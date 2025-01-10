import os
import logging
import asyncio
from datetime import datetime, timedelta

import discord
from discord.ext import commands

from bot_setup import cursor, conn, time_to_seconds, get_active_event, DB_PATH

class Commands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ... existing commands ...

    @commands.command(name="charts")
    async def charts(self, ctx):
        """Displays the current leaderboard (Charts) for the active event."""
        event = get_active_event()
        if not event:
            await ctx.send("⚠️ No active event found.")
            return

        event_id = event[0]
        event_name = event[1]
        channel_id = event[9]

        if ctx.channel.id != channel_id:
            await ctx.author.send("⚠️ This command can only be used in the event channel.")
            return

        if ctx.author.guild_permissions.administrator:
            leaderboard_msg = await self.generate_admin_leaderboard(event_id, event_name)
            await ctx.send(leaderboard_msg)
        else:
            leaderboard_msg = await self.generate_public_leaderboard(event_id, event_name)
            await ctx.send(leaderboard_msg)
            
            # Send DM to the user
            user_leaderboard_msg = await self.generate_user_leaderboard(event_id, event_name, ctx.author.id)
            await ctx.author.send(user_leaderboard_msg)

    async def generate_public_leaderboard(self, event_id, event_name):
        """Generates a formatted leaderboard for public view."""
        submissions = self.get_submissions(event_id)
        scores = {}
        for submission in submissions:
            score = self.calculate_score(submission[0])
            scores[submission[0]] = (submission[3], score, submission[4])  # Store song name, score, and URL

        sorted_scores = sorted(scores.items(), key=lambda x: x[1][1], reverse=True)

        leaderboard_msg = f"**🏆 {event_name} - Current Standings 🏆**\n\n"
        if not sorted_scores:
            leaderboard_msg += "No submissions yet!"
        else:
            for rank, (submission_id, (song_name, score, url)) in enumerate(sorted_scores, 1):
                leaderboard_msg += f"{rank}. [{song_name}]({url}) - **{score}** points\n"

        return leaderboard_msg

    async def generate_admin_leaderboard(self, event_id, event_name):
        """Generates a formatted leaderboard for admin view with vote details."""
        submissions = self.get_submissions(event_id)
        scores = {}
        users = {}
        for submission in submissions:
            score = self.calculate_score(submission[0])
            cursor.execute("SELECT user_id FROM submissions WHERE submission_id = ?", (submission[0],))
            user_id = cursor.fetchone()[0]
            cursor.execute("SELECT name FROM users WHERE user_id = ?", (user_id,))
            try:
                user_name = cursor.fetchone()[0]
            except TypeError:
                user_name = f"Unknown User (ID: {user_id})"

            
            if submission[0] not in scores:
                scores[submission[0]] = {
                    'song_name': submission[3],
                    'score': score,
                    'url': submission[4],
                    'submitter': user_name
                }

        sorted_scores = sorted(scores.items(), key=lambda x: x[1]['score'], reverse=True)

        leaderboard_msg = f"**🏆 {event_name} - Current Standings (Admin View) 🏆**\n\n"
        if not sorted_scores:
            leaderboard_msg += "No submissions yet!"
        else:
            for rank, (submission_id, submission_data) in enumerate(sorted_scores, 1):
                leaderboard_msg += f"{rank}. [{submission_data['song_name']}]({submission_data['url']}) (submitted by {submission_data['submitter']}) - **{submission_data['score']}** points\n"
                # Fetch and format votes for this submission
                cursor.execute("SELECT user_id, vote_value FROM votes WHERE submission_id = ?", (submission_id,))
                votes = cursor.fetchall()
                vote_details = ""
                for user_id, vote_value in votes:
                  cursor.execute("SELECT name FROM users WHERE user_id = ?", (user_id,))
                  try:
                      user_name = cursor.fetchone()[0]
                  except TypeError:
                      user_name = f"Unknown User (ID: {user_id})"
                  vote_details += f"  - {user_name}: {vote_value}\n"

                if vote_details:
                    leaderboard_msg += "  **Votes:**\n" + vote_details

        return leaderboard_msg

    async def generate_user_leaderboard(self, event_id, event_name, user_id):
        """Generates a formatted leaderboard for a specific user."""
        submissions = self.get_submissions(event_id)
        scores = {}
        for submission in submissions:
            score = self.calculate_score(submission[0])
            scores[submission[0]] = (submission[3], score, submission[4])  # Store song name, score, and URL

        sorted_scores = sorted(scores.items(), key=lambda x: x[1][1], reverse=True)

        leaderboard_msg = f"**🏆 {event_name} - Current Standings 🏆**\n\n"
        if not sorted_scores:
            leaderboard_msg += "No submissions yet!"
        else:
            for rank, (submission_id, (song_name, score, url)) in enumerate(sorted_scores, 1):
                leaderboard_msg += f"{rank}. [{song_name}]({url}) - **{score}** points\n"

        return leaderboard_msg
    
    # ... rest of the commands ...

    # Helper functions
    def get_event(self, event_id):
        """Retrieves event details from the database."""
        cursor.execute("SELECT * FROM events WHERE event_id = ?", (event_id,))
        return cursor.fetchone()

    def get_submissions(self, event_id):
        """Retrieves submissions for an event from the database."""
        cursor.execute("SELECT * FROM submissions WHERE event_id = ?", (event_id,))
        return cursor.fetchall()

    def calculate_score(self, submission_id):
        """Calculates the score for a submission."""
        cursor.execute("SELECT vote_value FROM votes WHERE submission_id = ?", (submission_id,))
        votes = cursor.fetchall()
        score = sum(vote[0] for vote in votes)
        return score
    
    # ... rest of the helper functions ...

def setup(bot):
    bot.add_cog(Commands(bot))