import sqlite3
import os
from datetime import datetime
import yaml

# Load configuration from YAML file
try:
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)
except FileNotFoundError:
    print("Error: config.yaml not found!")
    exit()

# Database setup (executed when this module is imported)
# Use a fixed path inside the container that corresponds to your volume mount
DB_PATH = os.path.join("/app/data", "countdown_bot.db")

print(f"DB_PATH: {DB_PATH}")  # Verify the path

def setup_db():
    """Creates the necessary database tables and ensures correct permissions."""
    db_dir = os.path.dirname(DB_PATH)

    # Ensure the database directory exists with correct permissions
    if not os.path.exists(db_dir):
        os.makedirs(db_dir, mode=0o755)  # Create directory with rwxr-xr-x permissions

    # Set permissions on the directory if it already exists
    os.chmod(db_dir, 0o755)

    # Ensure the database file has correct permissions (if it exists)
    if os.path.exists(DB_PATH):
        os.chmod(DB_PATH, 0o644)  # Set file permissions to rw-r--r--

    # Create tables if they don't exist
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
            highest_score INTEGER DEFAULT 0,
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
            submitter_name TEXT,
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
            voter_name TEXT,
            FOREIGN KEY (submission_id) REFERENCES submissions(submission_id)
        )
    """)
    conn.commit()

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

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
    result = cursor.fetchone()
    return result