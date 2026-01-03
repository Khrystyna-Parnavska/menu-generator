# Copilot / AI Agent Instructions

Purpose
- Help contributors and AI agents get productive quickly in this repository.

Big picture
- This project is a Python-based menu/recipe tool with two runtime modes:
  - CLI scripts (e.g. `main.py`, `setup_db.py`) that operate against a MySQL DB.
  - A small Flask demo app in `my_flask_app/app.py` using SQLite for local UI testing.
- Persistent data: `database/schema.sql`, models in `database/models.py`, and CSV fixtures in `data/`.

Key files to inspect (examples)
- [main.py](main.py): interactive CLI flow that builds a `DailyMenu` and saves summaries.
- [menu.py](menu.py): `DailyMenu` and `MealItem` dataclasses — core in-memory domain model.
- [setup_db.py](setup_db.py): creates schema and imports initial data (calls `database/db_connector.create_connection`).
- [database/db_connector.py](database/db_connector.py): reads DB credentials from environment variables via `dotenv`.
- [database/models.py](database/models.py): `BaseModel` pattern used across `MealsModel`, `RecipesModel`, etc.; CSV import logic is here.
- [data/recipes_test.csv](data/recipes_test.csv): example CSV used by `populate_from_csv`.

Project-specific conventions and gotchas
- Database connection: `create_connection()` uses env vars `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` (set in environment or .env). Keep those keys when creating or mocking connections.
- Docker hint: `setup_db.py` prints "Is Docker running?" — maintainers expect DB often run in Docker (there is a `docker-compose.yml`). If contributing DB-related code, check both local env and Docker settings.
- CSV import: `populate_from_csv` in `database/models.py` builds the INSERT by taking the intersection of the model's `columns` and CSV headers (it strips header whitespace and excludes `id`). When adding columns, ensure CSV header names match model `columns` exactly (no hidden spaces).
- Query pattern: `BaseModel.run_query` opens a new connection per call, uses `cursor(dictionary=True)` for SELECTs and commits non-SELECTs. Avoid persistent global cursors; follow the open/execute/close pattern.
- Naming quirk: `main.py` imports `meny` while the file is `menu.py`. Be cautious about module names and imports (this appears to be a typo/legacy name).

How to run common workflows (concrete)
- Run the interactive menu generator:
  - `python main.py`
- Create DB schema and load fixtures (expects DB reachable via env vars or Docker):
  - `python setup_db.py`
  - Confirm `.env` or environment contains the DB_* variables used by `database/db_connector.py`.
- Run the demo Flask app (local dev using SQLite):
  - `python my_flask_app/app.py`

Patterns to follow when changing code
- Add database columns: update the corresponding model class in `database/models.py` (the `columns` list) and update `database/schema.sql` accordingly. CSV imports rely on those lists.
- For data imports, prefer `populate_from_csv` rather than hand-crafted INSERTs — it handles header normalization and batch insert via `executemany`.
- Keep side-effecting scripts idempotent: `setup_db.py` runs many SQL commands split by `;` and uses transactions. If adding new scripts, respect begin/commit/rollback semantics.

When writing tests or experiments
- No formal test suite exists in the repo. For DB-affecting code, run `setup_db.py` against an isolated test DB or a local Docker MySQL instance to avoid clobbering production.
- For quick unit experiments, mock `database.db_connector.create_connection` to return a connection-like object.

If unsure or blocked
- Look at `database/models.py` and `setup_db.py` to understand DB expectations. If environment variables are missing, check for a `.env` file or start a local MySQL via the repository `docker-compose.yml`.

Ask me to iterate on this if any section is unclear or you'd like more examples.
