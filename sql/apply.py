"""
Runs a migration file from sql/ against the database in an env file, one statement at a time.

    venv/bin/python sql/apply.py .env.production sql/2026-10-25_pg.sql

It stops if the file's first new table already exists (so it can't run twice), and prints each statement as it
goes, so a failure shows exactly where it stopped.
"""

import re
import sys
from pathlib import Path

import MySQLdb


def read_env(path):
    env = {}
    for line in Path(path).read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def statements(sql):
    without_comments = "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())
    return [part.strip() for part in without_comments.split(";") if part.strip()]


def main(env_file, sql_file):
    env = read_env(env_file)
    parts = statements(Path(sql_file).read_text())
    first_table = next((re.search(r"CREATE TABLE `(\w+)`", p).group(1) for p in parts if "CREATE TABLE" in p), None)

    conn = MySQLdb.connect(
        host=env["DB_HOST"], port=int(env.get("DB_PORT", 3306)), user=env["DB_USER"], passwd=env["DB_PASSWORD"],
        db=env["DB_NAME"], ssl_mode="REQUIRED", connect_timeout=20,
    )
    cur = conn.cursor()
    print(f"Database: {env['DB_NAME']} on {env['DB_HOST'].split('.')[0]}…")
    if first_table:
        cur.execute("SHOW TABLES LIKE %s", [first_table])
        if cur.fetchone():
            print(f"`{first_table}` already exists: this migration has already run. Nothing done.")
            return
    for i, statement in enumerate(parts, 1):
        print(f"[{i}/{len(parts)}] {' '.join(statement.split())[:90]}")
        cur.execute(statement)
    conn.commit()
    print("Done. All statements ran.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
