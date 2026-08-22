"""
run_migration.py

Loads data/category_groups.csv, data/ingredient_categories.csv and
data/Ingredients_categories_map.csv into the database, using the project's
own create_connection() (mysql.connector + .env), not a separate driver.

IMPORTANT: this does NOT use BaseModel.populate_from_csv(). That method
always excludes the `id` column (correct for normal auto-increment inserts),
but this migration needs the exact ids preserved -- category_groups id 1-14
and Ingredient_categories id 101/401/etc. are referenced by foreign keys
elsewhere in this same package (group_id, category_id). Reassigning them via
auto-increment would silently break those relationships.

Order matters:
  1. Run 01_schema.sql first (creates category_groups, wipes/rebuilds
     Ingredient_categories, wipes Ingredients_categories_map).
  2. Run this script (loads the three CSVs, ids preserved).
  3. Run 02_fix_shopping_list.sql (repoints Shopping_list_ingredients).

Usage:
    python run_migration.py

Reads DB credentials the same way the rest of the app does -- via .env and
db_connector.create_connection(). No separate flags or env vars needed.

NOTE ON IMPORTS: this assumes the project layout is:

    project_root/
      database/
        db_connector.py
        models.py
      category_migration/     <- this folder
        run_migration.py      <- this file
      .env

i.e. `db_connector.py` lives in a `database` package at the project root
(matching how models.py imports it via `from .db_connector import ...`).
Run this script from the project root:

    python category_migration/run_migration.py

If your layout differs, adjust the import line below.
"""

import csv
import sys
from pathlib import Path

# Make the project root importable when running this script directly
# (assumes this file sits one level below the project root, e.g.
# project_root/category_migration/run_migration.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from database.db_connector import create_connection
except ImportError:
    sys.exit(
        "Could not import create_connection from database.db_connector.\n"
        "This script assumes db_connector.py lives in a `database/` package\n"
        "at your project root. If your layout differs, adjust the import\n"
        "at the top of this file (and run the script from wherever makes\n"
        "that import resolve)."
    )

DATA_DIR = Path(__file__).parent / "data"


def load_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def clean(value):
    """Empty string -> NULL, everything else stripped."""
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
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        
        groups = load_csv(DATA_DIR / "category_groups.csv")
        insert_rows(cursor, "Category_groups", groups, ["id", "name", "description"])
        print(f"  Category_groups: inserted {len(groups)} rows")

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
        print("\nDone. Data loaded successfully.")
        print("Next: run 02_fix_shopping_list.sql to repoint Shopping_list_ingredients.")
    except Exception as e:
        conn.rollback()
        print(f"\nMigration failed, rolled back -- nothing was committed.\n{e}", file=sys.stderr)
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
