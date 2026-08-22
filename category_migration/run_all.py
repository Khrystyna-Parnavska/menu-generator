"""
run_all.py

Runs the entire category migration in one command:
  1. 01_schema.sql
  2. load the three CSVs (same logic as run_migration.py)
  3. 02_fix_shopping_list.sql (including its sanity-check SELECTs, printed
     at the end so you can eyeball them without a separate mysql session)

Usage:
    python category_migration/run_all.py

Run from your project root, same assumptions as run_migration.py: this
imports `database.db_connector.create_connection`, matching how models.py
does it via `from .db_connector import ...`.
"""

import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from database.db_connector import create_connection
except ImportError:
    sys.exit(
        "Could not import create_connection from database.db_connector.\n"
        "Adjust the import at the top of this file if your layout differs."
    )

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"


def split_statements(sql_text):
    """
    Split a .sql file into individual statements. Strips '--' comments
    first, then splits on ';'. Good enough for straight-line DDL/DML
    without semicolons inside string literals (true for these two files --
    check your own .sql before reusing this on files that might have them).
    """
    # strip full-line and trailing '--' comments
    no_comments = re.sub(r"--.*", "", sql_text)
    statements = [s.strip() for s in no_comments.split(";")]
    return [s for s in statements if s]


def run_sql_file(cursor, path, fetch_results=False):
    text = path.read_text(encoding="utf-8")
    for stmt in split_statements(text):
        cursor.execute(stmt)
        if fetch_results and stmt.strip().upper().startswith("SELECT"):
            rows = cursor.fetchall()
            print(f"\n-- Result of: {stmt.splitlines()[0][:80]}...")
            for row in rows:
                print(" ", row)


def load_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def clean(value):
    if value is None:
        return None
    value = value.strip()
    return value if value != "" else None


def insert_rows(cursor, table, rows, columns):
    if not rows:
        return
    cols_str = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    sql = f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders})"
    values = [tuple(clean(row.get(c)) for c in columns) for row in rows]
    cursor.executemany(sql, values)


def main():
    conn = create_connection()
    if not conn:
        sys.exit("Could not connect to the database -- check your .env file.")

    cursor = conn.cursor()
    try:
        print("Step 1/3: running 01_schema.sql ...")
        run_sql_file(cursor, BASE_DIR / "01_schema.sql")
        conn.commit()
        print("  done.")

        print("Step 2/3: loading CSVs ...")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

        groups = load_csv(DATA_DIR / "category_groups.csv")
        insert_rows(cursor, "category_groups", groups, ["id", "name", "description"])
        print(f"  category_groups: inserted {len(groups)} rows")

        subcats = load_csv(DATA_DIR / "ingredient_categories.csv")
        insert_rows(cursor, "Ingredient_categories", subcats, ["id", "name", "group_id"])
        print(f"  Ingredient_categories: inserted {len(subcats)} rows")

        mapping = load_csv(DATA_DIR / "Ingredients_categories_map.csv")
        insert_rows(
            cursor,
            "Ingredients_categories_map",
            mapping,
            ["id", "ingredient_id", "category_id", "user_id", "source_id"],
        )
        print(f"  Ingredients_categories_map: inserted {len(mapping)} rows")

        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        conn.commit()
        print("  done.")

        print("Step 3/3: running 02_fix_shopping_list.sql ...")
        run_sql_file(cursor, BASE_DIR / "02_fix_shopping_list.sql", fetch_results=True)
        conn.commit()
        print("  done.")

        print("\nMigration complete. Review the sanity-check results printed above --")
        print("the 'orphaned category' query should have printed no rows.")
    except Exception as e:
        conn.rollback()
        print(f"\nMigration failed, rolled back -- nothing was committed.\n{e}", file=sys.stderr)
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
