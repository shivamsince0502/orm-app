"""Block until the Postgres database accepts connections (used by the container entrypoint)."""

import sys
import time

from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Wait for the database to become available."

    def handle(self, *args, **options):
        for attempt in range(60):
            try:
                connection.ensure_connection()
                self.stdout.write("Database is ready.")
                return
            except Exception as exc:
                if attempt == 0:
                    self.stdout.write("Waiting for database…")
                sys.stdout.flush()
                time.sleep(1)
        self.stderr.write("Database never became available.")
        sys.exit(1)
