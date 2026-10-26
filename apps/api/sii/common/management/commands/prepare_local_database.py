"""Migrate with the schema owner, then grant a separate non-owner local runtime identity."""

import os

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from psycopg import sql


class Command(BaseCommand):
    """Never provision production or allow a caller-selected SQL role/database identifier."""

    def handle(self, *args, **options):
        """Create a restricted runtime role; secrets are SQL parameters, never printed/argv."""
        if settings.ENVIRONMENT != "local" or connection.settings_dict["USER"] != "sii_local":
            raise CommandError("Requires the local schema owner.")
        password = os.environ.get("API_DB_PASSWORD", "")
        if len(password) < 50 or "GENERATE" in password:
            raise CommandError("Run setup to generate the separate runtime database credential.")
        call_command("migrate", interactive=False)
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname='sii_runtime'")
            if not cursor.fetchone():
                cursor.execute(
                    "CREATE ROLE sii_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT"
                )
            cursor.execute(
                sql.SQL("ALTER ROLE sii_runtime PASSWORD {}").format(sql.Literal(password))
            )
            cursor.execute("GRANT CONNECT ON DATABASE sii_local TO sii_runtime")
            cursor.execute("GRANT USAGE ON SCHEMA public TO sii_runtime")
            cursor.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            cursor.execute(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO sii_runtime"
            )
            cursor.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sii_runtime")
            cursor.execute("REVOKE ALL ON django_migrations FROM sii_runtime")
            # Django's startup migration check reads this ledger; runtime cannot alter it.
            cursor.execute("GRANT SELECT ON django_migrations TO sii_runtime")
            # Catalog changes are source-owned migrations, not runtime HTTP input.
            if "billing_plan" in connection.introspection.table_names():
                cursor.execute("REVOKE INSERT, UPDATE, DELETE ON billing_plan FROM sii_runtime")
        self.stdout.write("Local schema migrated; non-owner runtime grants configured.")
