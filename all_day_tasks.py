import sys
import os
from datetime import datetime

script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.append(script_dir)

from database.models import BaseModel 
from app import app, mail, local_time_to_utc_range
from flask_mail import Message

db_model = BaseModel('Recipes') 
user_model = BaseModel('Users')


def send_email(to, subject, body):
    try:
        msg = Message(subject, sender=app.config['MAIL_USERNAME'], recipients=[to])
        msg.body = body
        mail.send(msg)
        print(f"Email sent to {to}: {subject}")
    except Exception as e:
        print(f"Mail error: {e}")


def handle_reminders_and_journals():         
    with app.app_context():
        users = user_model.select_all()
        for user in users:
            user_id = user['id']
            user_tz = user.get('timezone') or user.get('time_zone') or 'UTC'

            _, _, local_now = local_time_to_utc_range(user_tz, return_now=True)

            # --- PART 1: MEAL REMINDERS (15m before Prep + Cook starts) ---
            # Triggers when current time is 15 mins away from (Meal Time - Total Work Time)
            reminder_query = """
                SELECT mm.id, u.email, r.name, r.prep_time, r.cooking_time, mm.meal_time
                FROM Menu_meals mm
                JOIN Menus m ON mm.menu_id = m.id
                JOIN Users u ON m.user_id = u.id
                JOIN Recipes r ON mm.recipe_id = r.id
                WHERE m.menu_date = %s 
                AND mm.reminder_sent = 0
                AND %s >= SUBTIME(mm.meal_time, sec_to_time(time_to_sec(cooking_time) + time_to_sec(prep_time)) + interval 15 minute)
                AND mm.meal_time > %s
                AND m.submitted_at IS NOT NULL
            """
            to_remind = db_model.run_query(reminder_query, (local_now.date(), local_now.time(), local_now.time()))
            
            for meal in (to_remind or []):
                total_work = meal['prep_time'] + meal['cooking_time']
                subject = f"🍳 Time to start: {meal['name']}"
                body = (f"Hi! It's time to head to the kitchen.\n\n"
                        f"Your meal is at {meal['meal_time']}.\n"
                        f"You have {total_work} minutes of prep and cooking ahead of you. Let's go!")
                
                send_email(meal['email'], subject, body)
                db_model.run_query("UPDATE Menu_meals SET reminder_sent = 1 WHERE id = %s", (meal['id'],))

            # --- PART 2: CREATE JOURNAL & REFLECTION EMAIL ---
            # Stays the same: Creates entry once the meal_time has passed
            journal_gen_query = """
                INSERT INTO Journal (user_id, menu_meal_id, meal_as_planned, meal_id, time_fact, mood)
                SELECT m.user_id, mm.id, 1, mm.meal_id, mm.meal_time, 5
                FROM Menu_meals mm
                JOIN Menus m ON mm.menu_id = m.id
                LEFT JOIN Journal j ON mm.id = j.menu_meal_id
                WHERE j.id IS NULL AND m.submitted_at IS NOT NULL
                AND m.menu_date = %s 
                AND mm.meal_time <= %s 
                AND m.user_id = %s
            """
            db_model.run_query(journal_gen_query, (local_now.date(), local_now.time(), user_id))

            # Notify user to fill out the journal
            notif_query = """
                SELECT j.id, u.email, r.name 
                FROM Journal j
                JOIN Menu_meals mm ON j.menu_meal_id = mm.id
                JOIN Recipes r ON mm.recipe_id = r.id
                JOIN Users u ON j.user_id = u.id
                WHERE j.user_id = %s AND mm.meal_time <= %s + INTERVAL 20 MINUTE AND j.notified = 0
            """
            to_notify = db_model.run_query(notif_query, (user_id, local_now.time()))
            for j in (to_notify or []):
                send_email(j['email'], "📝 Reflection Time", f"How was your {j['name']}? Your journal is ready.")
                db_model.run_query("UPDATE Journal SET notified = 1 WHERE id = %s", (j['id'],))


if __name__ == "__main__":
    handle_reminders_and_journals()