# Category redesign migration

Replaces the old flat `Ingredient_categories` list with a two-level
zone/subcategory structure, and repoints existing `Shopping_list_ingredients`
rows at the new category IDs.

## Contents

- `01_schema.sql` -- structural changes only (creates `category_groups`,
  rebuilds `Ingredient_categories` with a `group_id` link, clears the old
  ingredient->category map). No bulk data.
- `run_migration.py` -- loads the three CSVs in `data/` into the DB.
- `02_fix_shopping_list.sql` -- repoints `Shopping_list_ingredients.category_id`
  at the new IDs, then runs sanity-check queries.
- `data/category_groups.csv` -- the 14 store zones.
- `data/ingredient_categories.csv` -- the 66 subcategories, each linked to a zone.
- `data/Ingredients_categories_map.csv` -- every ingredient mapped to its one
  primary new category.

## Before you run anything

Back up both databases -- `01_schema.sql` truncates tables, and MySQL DDL
statements (`CREATE`, `ALTER`, `TRUNCATE`) auto-commit and can't be rolled back.

```
mysqldump -u USER -p DATABASE_NAME > backup_before_category_migration.sql
```

## Run order

1. **Schema** (via mysql client, phpMyAdmin, or PythonAnywhere's MySQL console):

   ```
   mysql -u USER -p DATABASE_NAME < 01_schema.sql
   ```

2. **Load data** (Python, uses your existing `db_connector.py` / `.env` -- no
   separate driver or flags needed, same as the rest of the app):

   ```
   python category_migration/run_migration.py
   ```

   Run this from your project root. `run_migration.py` imports
   `create_connection` from `database.db_connector` -- this assumes
   `db_connector.py` lives in a `database/` package at your project root
   (matching how `models.py` imports it via `from .db_connector import ...`).
   If that's not your actual layout, adjust the import at the top of
   `run_migration.py` accordingly.

   This deliberately does **not** use `BaseModel.populate_from_csv()` --
   that method always drops the `id` column on insert (correct for normal
   auto-increment rows), but this migration needs the exact category ids
   preserved (`101`, `401`, etc.), since they're referenced by foreign keys
   (`group_id`, `category_id`) elsewhere in this same package. Reassigning
   them via auto-increment would silently break those relationships.

3. **Fix shopping lists**:

   ```
   mysql -u USER -p DATABASE_NAME < 02_fix_shopping_list.sql
   ```

   The last three statements in this file are sanity checks -- read their
   output before trusting the app against the migrated data. In particular,
   the "orphaned category" query should return zero rows.

## Running this locally vs. on PythonAnywhere

Same three steps either way. On PythonAnywhere, run step 2 from a Bash
console with your app's virtualenv activated, from wherever `db_connector.py`
and its `.env` live:

```
workon menu-env-311   # or: source ~/menu-env-311/bin/activate
cd ~/path/to/your/project   # project root, wherever database/db_connector.py and .env are
python category_migration/run_migration.py
```

Since it reuses `create_connection()`, the same `.env` (`DB_HOST`, `DB_PORT`,
`DB_USER`, `DB_PASSWORD`, `DB_NAME`) that your deployed app already uses --
including the `Khrystyna$mysql_menu_generator_db` database name -- is picked
up automatically. No shell-escaping the `$` required, since it never touches
the command line.

## Notes

- `Case B` in `02_fix_shopping_list.sql` (custom shopping-list items with no
  linked ingredient) uses a best-guess old-category -> new-category mapping.
  It's lossy for ambiguous old categories (e.g. old "Produce" could have been
  fruit or veg) -- consider flagging those rows in the app for the user to
  double check rather than trusting them silently.
- This migration does not touch the `Ingredients` table itself, only
  categories and the mapping table.
