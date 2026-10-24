from pathlib import Path

from django.conf import settings
from django.db import connection
from django.test.runner import DiscoverRunner

SCHEMA = Path(settings.BASE_DIR) / "sql" / "schema.sql"


class VyntraTestRunner(DiscoverRunner):
    """
    The app's tables are unmanaged (no migrations), so the test database gets them from
    sql/schema.sql, plus the lookup rows the app expects.
    """

    def setup_databases(self, **kwargs):
        config = super().setup_databases(**kwargs)
        statements = [part.strip() for part in SCHEMA.read_text().split(";") if "CREATE TABLE" in part]
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
            cursor.execute(
                "INSERT INTO duration_type (name, code, is_active) VALUES "
                "('Day', 'DAY', 1), ('Month', 'MONTH', 1), ('Year', 'YEAR', 1)"
            )
            cursor.execute(
                "INSERT INTO business_type (name, code, description, is_active) "
                "VALUES ('Gym', 'GYM', 'Gym and fitness center', 1), "
                "('PG / Hostel', 'PG', 'Paying guest, hostel and co-living', 1)"
            )
        return config
