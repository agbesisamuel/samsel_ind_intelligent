"""Scoped, audited inventory APIs with concrete generated schema per resource type."""

from django.db import transaction
from django.urls import path
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.exceptions import MethodNotAllowed, NotFound, ValidationError
from rest_framework.response import Response

from sii.accounts.security import step_up
from sii.accounts.views import inputs
from sii.audit.services import record
from sii.tenants.models import Site
from sii.tenants.views import ScopedView

from . import models, serializers, services

RESOURCE_SERIALIZERS = {
    "buildings": serializers.BuildingSerializer,
    "zones": serializers.ZoneSerializer,
    "gateways": serializers.GatewaySerializer,
    "sensors": serializers.SensorSerializer,
    "calibrations": serializers.CalibrationSerializer,
    "sensor-commissionings": serializers.SensorCommissioningSerializer,
    "commissioning": serializers.SiteCommissioningSerializer,
    "commissioning-tests": serializers.CommissioningTestSerializer,
    "acceptances": serializers.AcceptanceSerializer,
}
REFERENCES = {
    "building_id": models.Building,
    "zone_id": models.Zone,
    "gateway_id": models.Gateway,
    "sensor_id": models.Sensor,
    "commissioning_id": models.SiteCommissioning,
}
EVIDENCE = {
    models.CalibrationRecord,
    models.SensorCommissioning,
    models.SiteCommissioning,
    models.CommissioningTest,
    models.CommissioningAcceptance,
}


class InventoryView(ScopedView):
    """Concrete route classes supply serializer/model; caller never chooses a Python model."""

    serializer_class = serializers.BuildingSerializer

    def site(self, write=False):
        """Require both URL tenant and exact site grant before looking up inventory."""
        return services.scoped_site(
            self.request.user, self.kwargs["org_id"], self.kwargs["site_id"], write
        )

    def items(self, site):
        """Scope the queryset before count, pagination, object lookup or nested relations."""
        return self.serializer_class.Meta.model.objects.filter(
            organisation=site.organisation, site=site
        ).order_by("id")

    def validate_references(self, data, site):
        """Resolve foreign UUIDs within one site; absent and foreign IDs are identical."""
        for field, model in REFERENCES.items():
            if (
                field in data
                and not model.objects.filter(
                    pk=data[field], organisation=site.organisation, site=site
                ).exists()
            ):
                raise NotFound()


class InventoryCollection(InventoryView):
    """List granted inventory and register scoped planned assets or append-only evidence."""

    def get(self, request, org_id, site_id):
        """Return paginated records only after exact scope resolution."""
        return self.listing(self.items(self.site()))

    def post(self, request, org_id, site_id):
        """Sensitive writes lock the site; QA alone records calibration, managers record drafts."""
        model = self.serializer_class.Meta.model
        if model == models.CommissioningAcceptance:
            raise MethodNotAllowed("POST")
        site = self.site(write=model != models.CalibrationRecord)
        if model == models.CalibrationRecord:
            services.require_qa(request.user, site)
        step_up(request)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            Site.objects.select_for_update().get(pk=site.pk)
            if model == models.Sensor:
                # Subscription lock follows the existing site lock. Capacity code
                # never takes a site/gateway lock afterwards, preventing a cycle.
                from sii.billing.services import ensure_capacity

                ensure_capacity(site.organisation_id, "sensor", site.pk)
            self.validate_references(serializer.validated_data, site)
            if (
                model == models.CalibrationRecord
                and serializer.validated_data["checked_at"] > timezone.now()
            ):
                raise ValidationError("Calibration cannot be future-dated.")
            kwargs = {"organisation": site.organisation, "site": site}
            if model in EVIDENCE:
                kwargs.update(recorded_by=request.user, synthetic=True)
            obj = serializer.save(**kwargs)
            record(
                "inventory.created",
                actor=request.user,
                organisation=site.organisation,
                site=site,
                subject=obj.pk,
                after=serializer.data,
            )
        return Response(serializer.data, status=201)


class InventoryDetail(InventoryView):
    """Read exact objects and amend configuration without deleting historical identities."""

    def get(self, request, org_id, site_id, object_id):
        """Foreign inventory IDs return the same response as absent IDs."""
        obj = self.items(self.site()).filter(pk=object_id).first()
        if not obj:
            raise NotFound()
        return Response(self.get_serializer(obj).data)

    def patch(self, request, org_id, site_id, object_id):
        """Evidence is append-only; hierarchy, external identity and lifecycle cannot be patched."""
        if self.serializer_class.Meta.model in EVIDENCE:
            raise MethodNotAllowed("PATCH")
        site = self.site(write=True)
        step_up(request)
        if not isinstance(request.data, dict):
            raise ValidationError("Expected an object.")
        if set(request.data) & {*REFERENCES, "building", "zone", "gateway", "external_id", "state"}:
            raise ValidationError("Inventory identity and hierarchy are immutable.")
        with transaction.atomic():
            Site.objects.select_for_update().get(pk=site.pk)
            obj = self.items(site).select_for_update().filter(pk=object_id).first()
            if not obj:
                raise NotFound()
            before = self.get_serializer(obj).data
            serializer = self.get_serializer(obj, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            record(
                "inventory.updated",
                actor=request.user,
                organisation=site.organisation,
                site=site,
                subject=obj.pk,
                before=before,
                after=serializer.data,
            )
        return Response(serializer.data)


class LifecycleView(InventoryView):
    """State changes are separate audited commands, with irreversible retirement."""

    @extend_schema(request=serializers.TransitionInput)
    def post(self, request, org_id, site_id, object_id):
        """Reject active transitions until real commissioning and later rule/route gates exist."""
        data = inputs(serializers.TransitionInput, request)
        site = self.site(write=True)
        obj = services.transition(
            request, site, self.serializer_class.Meta.model, object_id, data["target"]
        )
        return Response(self.get_serializer(obj).data)


class AcceptCommissioning(InventoryView):
    """Review a synthetic pack as QA; acceptance alone never enables monitoring."""

    serializer_class = serializers.AcceptanceSerializer

    @extend_schema(request=None, responses={201: serializers.AcceptanceSerializer})
    def post(self, request, org_id, site_id, object_id):
        """Keep authority independent from owner privileges and require fresh MFA."""
        result = services.accept_pack(request, self.site(), object_id)
        return Response(self.get_serializer(result).data, status=201)


class ActivationView(InventoryView):
    """Expose real activation blockers; no local input can turn synthetic records into approval."""

    serializer_class = serializers.ActivationResult

    def get(self, request, org_id, site_id):
        """Return missing rule, route and real acceptance gates to an authorized site reader."""
        return Response({"blockers": services.activation_gaps(self.site())})

    @extend_schema(request=None, responses={409: serializers.ActivationResult})
    def post(self, request, org_id, site_id):
        """Deny activation with explicit blockers, recording the attempt as evidence."""
        site = self.site(write=True)
        step_up(request)
        record(
            "site.activation_denied", actor=request.user, organisation=site.organisation, site=site
        )
        return Response({"blockers": services.activation_gaps(site)}, status=409)


def asset_routes():
    """Build concrete serializer-bound route classes for precise OpenAPI schemas."""
    routes = []
    prefix = "api/v1/organisations/<uuid:org_id>/sites/<uuid:site_id>/"
    for resource, serializer in RESOURCE_SERIALIZERS.items():
        name = serializer.Meta.model.__name__
        collection = type(
            name + "Collection",
            (InventoryCollection,),
            {
                "serializer_class": serializer,
                "__doc__": f"Scoped {name} collection.",
            },
        )
        # Isolate inherited method annotations so one resource cannot alter another's schema.
        collection = extend_schema_view(get=extend_schema(responses=serializer(many=True)))(
            collection
        )
        detail = type(
            name + "Detail",
            (InventoryDetail,),
            {
                "serializer_class": serializer,
                "__doc__": f"Scoped {name} detail.",
            },
        )
        routes.extend(
            [
                path(prefix + resource + "/", collection.as_view()),
                path(prefix + resource + "/<uuid:object_id>/", detail.as_view()),
            ]
        )
        if resource in {"gateways", "sensors"}:
            lifecycle = type(
                name + "Lifecycle",
                (LifecycleView,),
                {
                    "serializer_class": serializer,
                    "__doc__": f"Audited {name} lifecycle command.",
                },
            )
            routes.append(
                path(prefix + resource + "/<uuid:object_id>/transition/", lifecycle.as_view())
            )
    routes.extend(
        [
            path(prefix + "commissioning/<uuid:object_id>/accept/", AcceptCommissioning.as_view()),
            path(prefix + "activation/", ActivationView.as_view()),
        ]
    )
    return routes
