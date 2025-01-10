import os
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
bot = commands.Bot(command_prefix="/", intents=intents)

# Constants
VOTE_VALUES = {0: 5, 1: 3, 2: 1}  # Updated weighted scoring
WINNERS_CHANNEL_ID = config['bot']['winners_channel_id']

# Bot Events
@bot.event
async def on_ready():
    logging.info(f"Logged in as {bot.user.name} ({bot.user.id})")

    # Start background tasks for each active event
    cursor.execute("SELECT event_id FROM events WHERE active = 1")
    active_events = cursor.fetchall()

    for event in active_events:
        event_id = event[0]
        bot.loop.create_task(bot.get_cog("Commands").event_loop(event_id))

@bot.event
async def on_reaction_add(reaction, user):
    if user == bot.user:
        return

    message = reaction.message
    if not message.content.startswith("✅ Your song has been submitted as"):
        return

    # Extract track ID and event name from the message
    track_id = message.content.split("**")[1]
    event_name = message.content.split("**")[3]

    # Fetch event ID and submission ID using track ID and event name
    cursor.execute("SELECT event_id FROM events WHERE name = ?", (event_name,))
    event = cursor.fetchone()
    if not event:
        return
    event_id = event[0]

    cursor.execute("SELECT submission_id FROM submissions WHERE track_id = ? AND event_id = ?", (track_id, event_id))
    submission = cursor.fetchone()
    if not submission:
        return
    submission_id = submission[0]

    # Check if user has already voted 3 times for this event
    cursor.execute("SELECT COUNT(*) FROM votes WHERE submission_id IN (SELECT submission_id FROM submissions WHERE event_id = ?) AND user_id = ?", (event_id, user.id))
    vote_count = cursor.fetchone()[0]

    if vote_count >= 3:
        return

    # Other checks and code
    vote_value = VOTE_VALUES.get(vote_count, 1)

    cursor.execute("INSERT INTO votes (submission_id, user_id, vote_value, vote_time, voter_name) VALUES (?, ?, ?, ?, ?)", (submission_id, user.id, vote_value, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user.name))
    conn.commit()
    
    await bot.get_cog("Commands").update_event_message(event_id)

    score = bot.get_cog("Commands").calculate_score(submission_id)
    await bot.get_cog("Commands").check_milestones(event_id, submission_id, score)


    if score >= 100:
        await bot.get_cog("Commands").end_event(event_id)

# Load commands extension
bot.load_extension('commands')

# Run the bot
BOT_TOKEN = config['bot']['token']
bot.run(BOT_TOKEN)