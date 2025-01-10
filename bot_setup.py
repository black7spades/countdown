import sqlite3
import os
from datetime import datetime

# Database setup (executed when this module is imported)
DB_PATH = os.environ.get("DB_PATH", "/app/data/countdown_bot.db")  # Get DB path from environment variable
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

def setup_db():
    """Creates the necessary database tables."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            duration INTEGER,
            min_submissions INTEGER,
            max_submissions INTEGER,
            song_min_duration INTEGER,
            song_max_duration INTEGER,
            start_time TEXT,
            end_time TEXT,
            channel_id INTEGER,
            message_id INTEGER,
            active INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            submission_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER,
            user_id INTEGER,
            song_name TEXT,
            url TEXT,
            duration INTEGER,
            submission_time TEXT,
            track_id TEXT,
            milestone_reached BOOLEAN DEFAULT 0,
            FOREIGN KEY (event_id) REFERENCES events(event_id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS votes (
            vote_id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id INTEGER,
            user_id INTEGER,
            vote_value INTEGER,
            vote_time TEXT,
            FOREIGN KEY (submission_id) REFERENCES submissions(submission_id)
        )
    """)
    conn.commit()

setup_db()  # Call the function to create tables on module import

# Helper Functions
def time_to_seconds(time_str):
    """Converts a time string in the format 'MM:SS' to seconds."""
    try:
        minutes, seconds = map(int, time_str.split(':'))
        return minutes * 60 + seconds
    except ValueError:
        raise ValueError("Invalid time format. Use 'MM:SS'")

def get_active_event():
    """Retrieves the currently active event."""
    cursor.execute("SELECT * FROM events WHERE active = 1")
    return cursor.fetchone()