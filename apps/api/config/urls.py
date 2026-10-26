"""Explicit foundation and identity/tenant routes; no unrestricted Django admin surface."""

from django.urls import path
from drf_spectacular.views import SpectacularAPIView

from sii.accounts import views as auth
from sii.adapters import views as adapters
from sii.assets.views import asset_routes
from sii.billing import views as billing
from sii.common.views import HealthView, ReadinessView
from sii.incidents import views as incidents
from sii.monitoring import views as monitoring
from sii.notifications import views as notifications
from sii.reports import views as reports
from sii.rules import views as rules
from sii.support import desk
from sii.support import views as support
from sii.telemetry import views as telemetry
from sii.tenants import views as tenants

urlpatterns = [
    path("api/v1/plans/", billing.PlansView.as_view()),
    path("api/v1/organisations/<uuid:org_id>/subscription/", billing.SubscriptionView.as_view()),
    path(
        "api/v1/organisations/<uuid:org_id>/subscription/history/", billing.TermsHistory.as_view()
    ),
    path("api/v1/organisations/<uuid:org_id>/invoices/", billing.InvoicesView.as_view()),
    path(
        "api/v1/organisations/<uuid:org_id>/invoices/<uuid:invoice_id>/export/",
        billing.InvoiceExport.as_view(),
    ),
    path(
        "api/v1/support-sessions/<uuid:session_id>/diagnostics/", support.DiagnosticsView.as_view()
    ),
    path("api/v1/health/", HealthView.as_view(), name="health"),
    path("api/v1/ready/", ReadinessView.as_view(), name="ready"),
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/v1/auth/csrf/", auth.CSRFView.as_view()),
    path("api/v1/auth/login/", auth.LoginView.as_view()),
    path("api/v1/auth/logout/", auth.LogoutView.as_view()),
    path("api/v1/auth/invitations/accept/", auth.AcceptInvitationView.as_view()),
    path("api/v1/auth/password-reset/request/", auth.ResetRequestView.as_view()),
    path("api/v1/auth/password-reset/confirm/", auth.ResetConfirmView.as_view()),
    path("api/v1/auth/mfa/enroll/", auth.MFAEnrollView.as_view()),
    path("api/v1/auth/mfa/verify/", auth.MFAVerifyView.as_view()),
    path("api/v1/auth/step-up/", auth.StepUpView.as_view()),
    path("api/v1/me/", tenants.MeView.as_view()),
    path("api/v1/organisations/", tenants.OrganisationListView.as_view()),
    path("api/v1/organisations/<uuid:org_id>/", tenants.OrganisationDetailView.as_view()),
    path("api/v1/organisations/<uuid:org_id>/sites/", tenants.SiteListView.as_view()),
    path(
        "api/v1/organisations/<uuid:org_id>/sites/<uuid:site_id>/", tenants.SiteDetailView.as_view()
    ),
    path("api/v1/organisations/<uuid:org_id>/members/", tenants.MemberListView.as_view()),
    path(
        "api/v1/organisations/<uuid:org_id>/members/<uuid:membership_id>/",
        tenants.MemberDetailView.as_view(),
    ),
    path("api/v1/organisations/<uuid:org_id>/invitations/", tenants.InvitationListView.as_view()),
    path(
        "api/v1/organisations/<uuid:org_id>/invitations/<uuid:invitation_id>/revoke/",
        tenants.InvitationRevokeView.as_view(),
    ),
    path("api/v1/organisations/<uuid:org_id>/roles/", tenants.RoleGrantView.as_view()),
    path(
        "api/v1/organisations/<uuid:org_id>/roles/<uuid:role_id>/revoke/",
        tenants.RoleRevokeView.as_view(),
    ),
    path("api/v1/organisations/<uuid:org_id>/audit/", tenants.AuditListView.as_view()),
]
handler404 = "sii.common.errors.not_found"
handler500 = "sii.common.errors.server_error"
urlpatterns += asset_routes()
telemetry_prefix = "api/v1/organisations/<uuid:org_id>/sites/<uuid:site_id>/"
urlpatterns += [
    path(telemetry_prefix + "support-tickets/", desk.TicketsView.as_view()),
    path(
        telemetry_prefix + "support-tickets/<uuid:ticket_id>/events/",
        desk.TicketEventsView.as_view(),
    ),
    path(telemetry_prefix + "operational-status/", desk.OperationalStatus.as_view()),
    path(telemetry_prefix + "artifact-archive/", desk.ArtifactArchive.as_view()),
    path(telemetry_prefix + "adapter-readiness/", adapters.AdapterReadiness.as_view()),
    path(telemetry_prefix + "pilot-reviews/", adapters.ReviewsView.as_view()),
    path(telemetry_prefix + "support-sessions/", support.SessionsView.as_view()),
    path(telemetry_prefix + "support-access/", support.AccessView.as_view()),
    path(
        telemetry_prefix + "support-sessions/<uuid:session_id>/revoke/",
        support.RevokeView.as_view(),
    ),
    path(telemetry_prefix + "reports/", reports.ReportsView.as_view()),
    path(telemetry_prefix + "reports/<uuid:job_id>/retry/", reports.RetryView.as_view()),
    path(telemetry_prefix + "reports/<uuid:job_id>/access/", reports.GrantView.as_view()),
    path(
        telemetry_prefix + "reports/<uuid:job_id>/downloads/<uuid:grant_id>/",
        reports.DownloadView.as_view(),
    ),
    path(telemetry_prefix + "alert-contacts/", notifications.ContactsView.as_view()),
    path(telemetry_prefix + "alert-candidates/", notifications.CandidatesView.as_view()),
    path(
        telemetry_prefix + "alert-contacts/<uuid:contact_id>/confirm/",
        notifications.ContactConfirm.as_view(),
    ),
    path(
        telemetry_prefix + "alert-contacts/<uuid:contact_id>/disable/",
        notifications.ContactDisable.as_view(),
    ),
    path(telemetry_prefix + "alert-routes/", notifications.RoutesView.as_view()),
    path(
        telemetry_prefix + "alert-routes/<uuid:route_id>/enabled/",
        notifications.RouteEnabled.as_view(),
    ),
    path(
        telemetry_prefix + "alert-routes/<uuid:route_id>/test/", notifications.RouteTest.as_view()
    ),
    path(telemetry_prefix + "notifications/", notifications.NotificationsView.as_view()),
    path(telemetry_prefix + "notification-health/", notifications.HealthView.as_view()),
    path(telemetry_prefix + "rule-families/", rules.FamiliesView.as_view()),
    path(telemetry_prefix + "rule-versions/", rules.VersionsView.as_view()),
    path(
        telemetry_prefix + "rule-versions/<uuid:version_id>/backtests/",
        rules.BacktestView.as_view(),
    ),
    path(
        telemetry_prefix + "rule-versions/<uuid:version_id>/approve/", rules.ApprovalView.as_view()
    ),
    path(
        telemetry_prefix + "rule-versions/<uuid:version_id>/activate/", rules.ActivateView.as_view()
    ),
    path(telemetry_prefix + "maintenance/", rules.SuppressionView.as_view()),
    path(telemetry_prefix + "incidents/", incidents.IncidentsView.as_view()),
    path(telemetry_prefix + "incidents/<uuid:incident_id>/", incidents.IncidentDetail.as_view()),
    path(telemetry_prefix + "incidents/<uuid:incident_id>/events/", incidents.EventsView.as_view()),
    path(
        telemetry_prefix + "incidents/<uuid:incident_id>/commands/", incidents.CommandView.as_view()
    ),
    path(
        telemetry_prefix + "incidents/<uuid:incident_id>/assignees/",
        incidents.AssigneesView.as_view(),
    ),
    path(
        telemetry_prefix + "incidents/<uuid:incident_id>/attachments/",
        incidents.AttachmentsView.as_view(),
    ),
    path(
        telemetry_prefix
        + "incidents/<uuid:incident_id>/attachments/<uuid:attachment_id>/download/",
        incidents.AttachmentDownload.as_view(),
    ),
    path(
        telemetry_prefix + "incidents/<uuid:incident_id>/notifications/",
        incidents.IncidentNotifications.as_view(),
    ),
    path(
        telemetry_prefix + "incidents/<uuid:incident_id>/activity/",
        incidents.ActivityExport.as_view(),
    ),
    path(telemetry_prefix + "freshness-policy/", monitoring.PolicyView.as_view()),
    path(telemetry_prefix + "monitoring/", monitoring.DashboardView.as_view()),
    path(telemetry_prefix + "series/", monitoring.SeriesView.as_view()),
    path(telemetry_prefix + "latency/", monitoring.LatencyView.as_view()),
    path(telemetry_prefix + "device-credentials/", telemetry.CredentialsView.as_view()),
    path(
        telemetry_prefix + "device-credentials/<uuid:credential_id>/revoke/",
        telemetry.RevokeView.as_view(),
    ),
    path(telemetry_prefix + "readings/", telemetry.ReadingsView.as_view()),
    path(telemetry_prefix + "ingestion-metrics/", telemetry.MetricsView.as_view()),
    path(telemetry_prefix + "csv-import/", telemetry.CSVView.as_view()),
]
