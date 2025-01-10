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

    @commands.command(name="countdownstart")
    @commands.has_permissions(administrator=True)
    async def countdownstart(self, ctx):
        """Start a new countdown event."""
        await ctx.send("🎉 **Countdown Event Setup!** What is the name of your event?")

        def check(msg):
            return msg.author == ctx.author and msg.channel == ctx.channel

        try:
            # Collect event details
            name_msg = await self.bot.wait_for("message", check=check, timeout=60)
            event_name = name_msg.content

            await ctx.send("⏳ How long should the event last? (e.g., `7 days`)")
            duration_msg = await self.bot.wait_for("message", check=check, timeout=60)
            duration = int(duration_msg.content)

            await ctx.send("📥 Minimum number of submissions required?")
            min_msg = await self.bot.wait_for("message", check=check, timeout=60)
            min_submissions = int(min_msg.content)

            await ctx.send("📥 Maximum number of submissions allowed?")
            max_msg = await self.bot.wait_for("message", check=check, timeout=60)
            max_submissions = int(max_msg.content)

            await ctx.send("🎵 Minimum song duration? (e.g., `2:30`)")
            min_dur_msg = await self.bot.wait_for("message", check=check, timeout=60)
            min_duration = time_to_seconds(min_dur_msg.content)

            await ctx.send("🎵 Maximum song duration? (e.g., `4:20`)")
            max_dur_msg = await self.bot.wait_for("message", check=check, timeout=60)
            max_duration = time_to_seconds(max_dur_msg.content)

            # Calculate end time
            start_time = datetime.now()
            end_time = start_time + timedelta(days=duration)

            # Insert into database
            cursor.execute("""
                INSERT INTO events (name, duration, min_submissions, max_submissions, song_min_duration, song_max_duration, start_time, end_time, channel_id, active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (event_name, duration, min_submissions, max_submissions, min_duration, max_duration, start_time.strftime("%Y-%m-%d %H:%M:%S"), end_time.strftime("%Y-%m-%d %H:%M:%S"), ctx.channel.id))
            event_id = cursor.lastrowid
            conn.commit()

            embed = discord.Embed(title=f"Countdown Event: {event_name}", description="Current Standings:")
            embed.add_field(name="No Submissions Yet!", value="\u200b", inline=False)
            time_left = end_time - datetime.now()
            embed.set_footer(text=f"Time left: {time_left}")

            message = await ctx.send(embed=embed)

            cursor.execute("UPDATE events SET message_id = ? WHERE event_id = ?", (message.id, event_id))
            conn.commit()

            logging.info(f"Event started: {event_name} (ID: {event_id})")

            # Start the event loop for this event
            self.bot.loop.create_task(self.event_loop(event_id))

            await ctx.send(f"✅ **Countdown Event '{event_name}' created!** Submissions are now open!")

        except asyncio.TimeoutError:
            await ctx.send("⚠️ **You took too long to respond. Event setup cancelled.**")
        except Exception as e:
            logging.error(f"Error during event setup: {e}")
            await ctx.send("⚠️ **Error setting up the event. Please try again!**")

    @commands.command(name="submitsong")
    async def submitsong(self, ctx):
        """Submit a song to the active event."""
        event = get_active_event()
        if not event:
            await ctx.author.send("⚠️ No active Countdown Event. Submissions are closed.")
            return

        event_id = event[0]
        await ctx.author.send("🎵 Let's submit your song! What's the name of your song?")

        def check_dm(msg):
            return msg.author == ctx.author and isinstance(msg.channel, discord.DMChannel)

        try:
            # Collect and validate song details
            name_msg = await self.bot.wait_for("message", check=check_dm, timeout=60)
            song_name = name_msg.content

            await ctx.author.send("🔗 Provide the URL for your song.")
            url_msg = await self.bot.wait_for("message", check=check_dm, timeout=60)
            song_url = url_msg.content

            await ctx.author.send("⏳ What is the duration of the song? (e.g., `3:42`)")
            duration_msg = await self.bot.wait_for("message", check=check_dm, timeout=60)
            song_duration = duration_msg.content

            min_dur_sec = event[5]
            max_dur_sec = event[6]
            song_dur_sec = time_to_seconds(song_duration)

            if not (min_dur_sec <= song_dur_sec <= max_dur_sec):
                await ctx.author.send(f"⚠️ Invalid song duration. It must be between {event[5]} and {event[6]}.")
                return

            track_id = f"Track-{len(cursor.execute('SELECT * FROM submissions WHERE event_id = ?', (event_id,)).fetchall()) + 1}"
            cursor.execute("""
                INSERT INTO submissions (event_id, user_id, song_name, url, duration, submission_time, track_id, submitter_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (event_id, ctx.author.id, song_name, song_url, song_dur_sec, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), track_id, ctx.author.name))
            conn.commit()

            logging.info(f"Submission received for event ID {event_id}: {song_name} ({song_url})")
            cursor.execute("SELECT name FROM events WHERE event_id = ?", (event_id,))
            event_name = cursor.fetchone()[0]
            await ctx.author.send(f"✅ Your song has been submitted as **{track_id}** to event **{event_name}**. Check the event channel to react with your 3 votes and update the standings!")
            await self.update_event_message(event_id)

        except asyncio.TimeoutError:
            await ctx.author.send("⚠️ **You took too long to respond. Submission cancelled.**")
        except ValueError:
            await ctx.author.send("⚠️ **Invalid duration format. Please use `MM:SS`.**")
        except Exception as e:
            logging.error(f"Error during song submission: {e}")
            await ctx.author.send("⚠️ **Error submitting your song. Please try again!**")

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
        for submission in submissions:
            score = self.calculate_score(submission[0])
            
            if submission[0] not in scores:
                scores[submission[0]] = {
                    'song_name': submission[3],
                    'score': score,
                    'url': submission[4],
                    'submitter': submission[7]
                }

        sorted_scores = sorted(scores.items(), key=lambda x: x[1]['score'], reverse=True)

        leaderboard_msg = f"**🏆 {event_name} - Current Standings (Admin View) 🏆**\n\n"
        if not sorted_scores:
            leaderboard_msg += "No submissions yet!"
        else:
            for rank, (submission_id, submission_data) in enumerate(sorted_scores, 1):
                leaderboard_msg += f"{rank}. [{submission_data['song_name']}]({submission_data['url']}) (submitted by {submission_data['submitter']}) - **{submission_data['score']}** points\n"
                # Fetch and format votes for this submission
                cursor.execute("SELECT voter_name, vote_value FROM votes WHERE submission_id = ?", (submission_id,))
                votes = cursor.fetchall()
                vote_details = ""
                for voter_name, vote_value in votes:
                  vote_details += f"  - {voter_name}: {vote_value}\n"

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

    async def event_loop(self, event_id):
        """Background loop for each active event."""
        while True:
            event = self.get_event(event_id)
            if not event or event[10] == 0:  # Check if event is inactive or message id is null
                break

            current_time = datetime.now()
            end_time = datetime.strptime(event[7], "%Y-%m-%d %H:%M:%S")

            if current_time >= end_time:
                await self.end_event(event_id)
                break

            await self.update_event_message(event_id)
            await asyncio.sleep(60)  # Check every 60 seconds

    async def update_event_message(self, event_id):
        """Updates the event message with current standings."""
        event = self.get_event(event_id)
        if not event:
            return

        channel_id = event[9]
        message_id = event[10]
        channel = self.bot.get_channel(channel_id)

        try:
            message = await channel.fetch_message(message_id)

            submissions = self.get_submissions(event_id)
            scores = {}
            for submission in submissions:
                score = self.calculate_score(submission[0])
                scores[submission[3]] = score

            sorted_scores = sorted(scores.items(), key=lambda x: x[1][1], reverse=True)

            embed = discord.Embed(title=f"Countdown Event: {event[1]}", description="Current Standings:")

            if not sorted_scores:
                embed.add_field(name="No Submissions Yet!", value="\u200b", inline=False)
            else:
                for song, score in sorted_scores:
                    embed.add_field(name=song, value=f"Score: {score}", inline=False)

            current_time = datetime.now()
            end_time = datetime.strptime(event[7], "%Y-%m-%d %H:%M:%S")

            time_left = end_time - current_time
            embed.set_footer(text=f"Time left: {time_left}")

            await message.edit(embed=embed)

        except discord.NotFound:
            logging.error(f"Message with ID {message_id} not found in channel {channel_id}.")
        except Exception as e:
            logging.error(f"Error updating event message: {e}")

    async def check_milestones(self, event_id, submission_id, score):
        """Checks for milestones and sends announcements."""
        event = self.get_event(event_id)
        if not event:
            return

        channel_id = event[9]
        channel = self.bot.get_channel(channel_id)
        submission = None
        submissions = self.get_submissions(event_id)
        for sub in submissions:
            if sub[0] == submission_id:
                submission = sub
                break

        if not submission:
            return

        song_name = submission[3]
        total_points_for_100 = 100

        for milestone in [0.25, 0.5, 0.75, 1.0]:
            target_score = total_points_for_100 * milestone

            if score >= target_score:
                cursor.execute("SELECT milestone_reached FROM submissions WHERE submission_id = ?", (submission_id,))
                result = cursor.fetchone()
                milestone_reached = bool(result[0]) if result else False

                if not milestone_reached:
                    try:
                        await channel.send(f"🎉 {song_name} has reached {int(milestone * 100)}% of the goal with {score} points!")
                    except Exception as e:
                        logging.error(f"Failed to send milestone message: {e}")

                    cursor.execute("UPDATE submissions SET milestone_reached = ? WHERE submission_id = ?", (True, submission_id))
                    conn.commit()

    async def end_event(self, event_id):
        """Ends the event and displays the results."""
        event = self.get_event(event_id)
        if not event:
            return

        channel_id = event[9]
        channel = self.bot.get_channel