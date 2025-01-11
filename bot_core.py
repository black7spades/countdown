import os
import sqlite3  # Import the sqlite3 module

# Get the absolute path of the directory where bot_setup.py is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Construct the absolute path to the database file
DB_PATH = os.path.join(BASE_DIR, "/data/countdown_bot.db")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
import logging
import asyncio
from datetime import datetime, timedelta

import discord
from discord.ext import commands

from bot_setup import conn, cursor, get_active_event, setup_db, DB_PATH, config

# Configure logging
logging.basicConfig(level=config['bot']['log_level'])

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)

async def setup_hook() -> None:
    """Loads commands extension and starts event loops for active events."""
    cursor.execute(
        (
            "SELECT event_id "
            "FROM events "
            "WHERE active = 1"
        )
    )
    active_events = cursor.fetchall()

    for event in active_events:
        event_id = event[0]
        bot.loop.create_task(bot.get_cog("Commands").event_loop(event_id))
    await bot.load_extension('commands')

# Constants
VOTE_VALUES = {0: 5, 1: 3, 2: 1}  # Updated weighted scoring
WINNERS_CHANNEL_ID = config['bot']['winners_channel_id']

# Bot Events
@bot.event
async def on_ready():
    logging.info(f"Logged in as {bot.user.name} ({bot.user.id})")

@bot.event
async def on_reaction_add(reaction, user):
    """Handles vote recording when a reaction is added to a submission message."""
    if user == bot.user:
        return

    message = reaction.message
    if not message.content.startswith("✅ Your song has been submitted as"):
        return

    # Extract track ID and event name from the message
    track_id = message.content.split("**")[1]
    event_name = message.content.split("**")[3]

    # Fetch event ID and submission ID using track ID and event name
    cursor.execute(
        (
            "SELECT event_id "
            "FROM events "
            "WHERE name = ?"
        ),
        (event_name,)
    )
    event = cursor.fetchone()
    if not event:
        logging.warning(f"Event not found for name: {event_name}")
        return
    event_id = event[0]

    cursor.execute(
        (
            "SELECT submission_id "
            "FROM submissions "
            "WHERE track_id = ? AND event_id = ?"
        ),
        (track_id, event_id)
    )
    submission = cursor.fetchone()
    if not submission:
        logging.warning(f"Submission not found for track ID: {track_id} in event: {event_id}")
        return
    submission_id = submission[0]

    # Check if user has already voted 3 times for this event
    cursor.execute(
        (
            "SELECT COUNT(*) "
            "FROM votes "
            "WHERE submission_id IN ("
            "    SELECT submission_id "
            "    FROM submissions "
            "    WHERE event_id = ?"
            ") "
            "AND user_id = ?"
        ),
        (event_id, user.id)
    )
    vote_count = cursor.fetchone()[0]

    if vote_count >= 3:
        logging.info(f"User {user.name} has already voted 3 times for event {event_id}")
        return

    # Record the vote
    vote_value = VOTE_VALUES.get(vote_count, 1)
    cursor.execute(
        (
            "INSERT INTO votes (submission_id, user_id, vote_value, vote_time, voter_name) "
            "VALUES (?, ?, ?, ?, ?)"
        ),
        (submission_id, user.id, vote_value, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user.name)
    )
    conn.commit()
    logging.info(f"Vote recorded for submission {submission_id} by user {user.name} (value: {vote_value})")
    
    # Update event message and check milestones
    commands_cog = bot.get_cog("Commands")
    await commands_cog.update_event_message(event_id)
    score = commands_cog.calculate_score(submission_id)
    await commands_cog.check_milestones(event_id, submission_id, score)

    if score >= 100:
        await commands_cog.end_event(event_id)

# Run the bot
BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot.run(BOT_TOKEN)