import sys
import os
from datetime import datetime

# 1. Path Setup
project_home = u'/menu_generator' # Ensure this matches your PA path
if project_home not in sys.path:
    sys.path.append(project_home)

# 2. Imports
from database.models import BaseModel 
from app import app, mail, local_time_to_utc_range
from flask_mail import Message

# Initialize models
# Using one model instance for general queries is often cleaner
db_model = BaseModel('Recipes') 
user_model = BaseModel('Users')

def generate_pending_journals():
    """Finds passed meals and creates empty journal reflections."""
    print(f"[{datetime.now()}] Starting journal generation...")
    
    users = user_model.select_all()
    if not users:
        return

    for user in users:
        user_id = user['id']
        # FIX: Ensure we use the correct key for timezone (check your DB column name)
        user_tz = user.get('timezone') or user.get('time_zone') or 'UTC'
        
        # Get the 3rd item from the tuple (local_now)
        time_data = local_time_to_utc_range(user_tz, return_now=True)
        user_time_now = time_data[2] 
        
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
            db_model.run_query(query, (user_time_now.date(), user_time_now.time(), user_id))
        except Exception as e:
            print(f"Error generating journal for user {user_id}: {e}")

    print(f"[{datetime.now()}] Journal generation complete.")


def send_meal_reminders():
    """Sends email notifications for upcoming meals."""
    with app.app_context():
        print(f"[{datetime.now()}] Running meal reminder job...")
        
        all_users = user_model.select_all()

        for user_data in all_users:
            user_id = user_data['id']
            # FIX: Match the timezone key consistency
            user_tz = user_data.get('timezone') or user_data.get('time_zone') or 'UTC'

            _, _, local_now = local_time_to_utc_range(user_tz, return_now=True)
            
            query = """
                SELECT mm.id, m.menu_date, u.email, r.name as recipe_name, mm.meal_time
                FROM Menu_meals mm
                JOIN Menus m ON mm.menu_id = m.id
                JOIN Users u ON m.user_id = u.id
                JOIN Recipes r ON mm.recipe_id = r.id
                WHERE mm.meal_time BETWEEN %s AND DATE_ADD(%s, INTERVAL 1 HOUR)
                AND m.user_id = %s 
                AND m.submitted_at IS NOT NULL
                AND m.menu_date = %s
                AND mm.reminder_sent = 0
            """
            
            upcoming_meals = db_model.run_query(query, (
                local_now.time(), 
                local_now.time(), 
                user_id, 
                local_now.date()
            ))

            if not upcoming_meals:
                continue

            for meal in upcoming_meals:
                try:
                    msg = Message("🍳 Time to Cook!",
                                  sender=app.config['MAIL_USERNAME'],
                                  recipients=[meal['email']])

                    menu_url = "https://yourusername.pythonanywhere.com/menu"

                    msg.html = f"""
                    <div style="font-family: sans-serif; max-width: 400px; margin: auto; border: 1px solid #5d3f9b; padding: 20px; border-radius: 15px; text-align: center; background-color: #f9f9f9;">
                        <h2 style="color: #ff66b2;">Kitchen Time!</h2>
                        <p>It's almost time for your <strong>{meal['recipe_name']}</strong>.</p>
                        <p>Scheduled for: <strong>{meal['meal_time']}</strong></p>
                        <a href="{menu_url}" style="background-color: #5d3f9b; color: white; padding: 10px 20px; text-decoration: none; border-radius: 25px; display: inline-block;">View Recipe</a>
                    </div>
                    """
                    
                    mail.send(msg)
                    
                    # Mark as sent
                    db_model.run_query("UPDATE Menu_meals SET reminder_sent = 1 WHERE id = %s", (meal['id'],))
                    print(f"Success: Reminder sent to {meal['email']}")
                    
                except Exception as e:
                    print(f"Failed to send email for meal {meal['id']}: {e}")

if __name__ == "__main__":
    # Order matters: Send reminders first so they aren't delayed by journal generation
    send_meal_reminders()
    generate_pending_journals()