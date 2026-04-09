import sys
import os
from datetime import datetime

# 1. Path Setup
project_home = u'/home/khrystyna/menu_generator'
if project_home not in sys.path:
    sys.path.append(project_home)

# 2. Imports
from database.models import BaseModel 
from app import local_time_to_utc_range

# Initialize models
journal_model = BaseModel('Journal')
user_model = BaseModel('Users')

def generate_pending_journals():
    print(f"[{datetime.now()}] Starting journal generation...")
    
    users = user_model.select_all()
    if not users:
        return

    for user in users:
        user_id = user['id']
        user_tz = user.get('time_zone') or 'UTC'
        
        # FIX 1: Get the 3rd item from the tuple (local_now)
        time_data = local_time_to_utc_range(user_tz, return_now=True)
        user_time_now = time_data[2] 
        
        # FIX 2 & 3: Match table names and add date logic
        query = """
        INSERT INTO Journal (user_id, menu_meal_id, meal_as_planned, created_at)
        SELECT mm.user_id, mm.id, 1, CURRENT_TIMESTAMP
        FROM Menu_meals mm
        JOIN Menus m ON mm.menu_id = m.id
        LEFT JOIN Journal j ON mm.id = j.menu_meal_id
        WHERE j.id IS NULL 
        AND m.menu_date = %s
        AND mm.meal_time <= %s
        AND m.user_id = %s
        """
        
        try:
            # Pass today's date and the current time
            journal_model.run_query(query, (user_time_now.date(), user_time_now.time(), user_id))
        except Exception as e:
            print(f"Error for user {user_id}: {e}")

    print(f"[{datetime.now()}] Generation complete.")

if __name__ == "__main__":
    generate_pending_journals()