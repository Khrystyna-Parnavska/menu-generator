import csv
from .db_connector import create_connection


class BaseModel:
    """Base model to provide database db."""

    def __init__(self, table_name):
        self.table_name = table_name
        self.columns = []
        self.fetch_column_names()

    def fetch_column_names(self) -> None:
        """Fetch column names once and close connection immediately."""
        db = create_connection()
        if db:
            cursor = db.cursor(dictionary=True)
            try:
                # We use a direct cursor here to keep the logic contained
                cursor.execute(f"DESCRIBE {self.table_name}")
                results = cursor.fetchall()
                self.columns = [row['Field'] for row in results]
            except Exception:
                # Table might not exist yet during the very first run of setup_db.py
                self.columns = []
            finally:
                cursor.close()
                db.close()

    def run_query(self, query, params:tuple = ()):
        """
        Run a given SQL query with optional parameters.
        Args:
            query (str): The SQL query to execute.
            params (tuple, optional): Parameters for the SQL query. Defaults to None.
        Returns: The result of the query, if inserting, returns last inserted ID."""
        db = create_connection()
        if db:
            cursor = db.cursor(dictionary=True)
            try:
                cursor.execute(query, params or ())
                if query.strip().upper().startswith("SELECT"):
                    results = cursor.fetchall()
                else:
                    # COMMIT the changes so they are visible to other queries
                    db.commit()
                    # RETURN the last inserted ID for Foreign Key use
                    results = cursor.lastrowid # int
                return results
            except Exception as e:
                print(f"Query Error: {e}")
                return None
            finally:
                # print(f"query executed: {query}")
                # print(f"with params: {params}")
                # print('Closing connection')
                # print('-'*20)
                cursor.close()
                db.close()
        else:
            print("No database available.")
            return None
        
    def delete_all(self):
        """Delete all records from the table."""
        query = f"DELETE FROM {self.table_name}"
        return self.run_query(query)
    
    def delete(self, record_id):
        """Delete a record by its ID."""
        query = f"DELETE FROM {self.table_name} WHERE id = %s"
        return self.run_query(query, (record_id,))
    
    def insert(self, data: dict):
        """Insert a new record into the table."""
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['%s'] * len(data))
        values = tuple(data.values())
        query = f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders})"
        return self.run_query(query, values)
    
    def insert_many(self, data_list: list):
        """Insert multiple records into the table."""
        new_ids = []
        for data in data_list:
            if list(data.keys()) != self.columns[1:]:  # Exclude 'id'
                print(f"Error: Data keys {list(data.keys())} do not match model columns {self.columns[1:]}")
                return None
            else:
                columns = ', '.join(data_list[0].keys())
                placeholders = ', '.join(['%s'] * len(data_list[0]))
                query = f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders})"
                values = tuple(data.values())
                new_id = self.run_query(query, values)
                new_ids.append(new_id)
        return new_ids
    
    def update(self, record_id, data: dict):
        """Update a record by its ID."""
        set_clause = ', '.join([f"{key} = %s" for key in data.keys()])
        values = tuple(data.values()) + (record_id,)
        query = f"UPDATE {self.table_name} SET {set_clause} WHERE id = %s"
        return self.run_query(query, values)
    
    def select_by_id(self, record_id):
        """Retrieve a record by its ID."""
        query = f"SELECT * FROM {self.table_name} WHERE id = %s"
        results = self.run_query(query, (record_id,))
        return results[0] if results else None
    
    def select_all(self):
        """Retrieve all records from the table."""
        query = f"SELECT * FROM {self.table_name}"
        return self.run_query(query)
    
    def filter_by(self, **conditions):
        """Retrieve records matching given conditions."""
        where_clause = ' AND '.join([f"{key} = %s" for key in conditions.keys()])
        values = tuple(conditions.values())
        query = f"SELECT * FROM {self.table_name} WHERE {where_clause}"
        return self.run_query(query, values)
    
    def populate_from_csv(self, file_path, table_name, delimiter=',', encoding='utf-8'):
        """
        Reads a CSV and inserts data based on the columns 
        defined in the child class (e.g., self.columns).
        """
        db = create_connection()
        if db:
            cursor = db.cursor()
            cursor.execute(f"DESCRIBE {table_name}")
            column_names = [col[0] for col in cursor.fetchall()]
            print(f"Table '{table_name}' columns: {column_names}")
        else:
            print("No database available.")

        try:
            print(f"Importing data from {file_path} into {table_name}...")
            with open(file_path, mode='r', encoding=encoding) as f:
                reader = csv.DictReader(f, delimiter=delimiter)
                # Clean headers to avoid hidden space issues
                csv_headers = [name.strip() for name in reader.fieldnames]
                reader.fieldnames = csv_headers

                # 1. FIND THE INTERSECTION
                # We only use columns that are both in your Model AND in the CSV
                # (Excluding 'id' because it's auto-increment)
                cols_to_use = [col for col in column_names if col in csv_headers and col != 'id']
                    
                if not cols_to_use:
                    print(f"❌ Error: No matching columns found between Model and CSV.")
                    return 

                # 2. DYNAMICALLY BUILD THE SQL
                columns_str = ", ".join(cols_to_use)
                placeholders = ", ".join(["%s"] * len(cols_to_use))
                sql = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"

                rows_to_insert = []
                for row in reader:
                    # --- PASTE THE FIX HERE ---
                    values = []
                    for col in cols_to_use:
                        val = row.get(col)
                        # val.strip() removes hidden spaces; 
                        # 'if val is not None' prevents crashing on empty cells
                        values.append(val.strip() if val is not None else None)
                    
                    rows_to_insert.append(tuple(values))
                if rows_to_insert:
                    cursor.executemany(sql, rows_to_insert)
                    db.commit()
                    print(f"✅ Successfully imported {len(rows_to_insert)} rows into {table_name}")
                    # print(f"Columns used: {cols_to_use}")

        except Exception as e:
            print(f"❌ CSV Import Error: {e}")
            db.rollback()
        finally:
            cursor.close()
            db.close()
if __name__ == "__main__":    # Example usage
    pass