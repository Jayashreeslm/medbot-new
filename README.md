# MEDBOT — Intelligent Pill Dispenser and Patient Assistance System

## Setup (Step 1: Auth + Database — complete)

1. Create a virtual environment (recommended):
   python -m venv venv
   venv\Scripts\activate   (Windows)  OR  source venv/bin/activate (Mac/Linux)

2. Install dependencies:
   pip install -r requirements.txt

3. Copy .env.example to .env and fill in values as needed (all optional for now).

4. Run the app:
   python app.py

5. Open http://localhost:5000 in your browser.

## What's working so far
- Landing page
- Registration (patient + caretaker details, validated Indian mobile numbers, hashed passwords)
- Login / Logout with Flask sessions
- Protected dashboard (redirects to login if not authenticated)
- Profile page
- SQLite database with all 7 core tables (users, medicines, schedules, medicine_history, notifications, hardware, battery)
- Every new patient automatically gets isolated hardware + battery records

## Next steps
- Medicine management (add/edit/delete/search, compartments, stock)
- Scheduling + reminders (APScheduler)
- Face recognition
- Notifications (Twilio + simulation mode)
- Hardware integration (ESP32) + simulation mode
- Medicine + notification history
