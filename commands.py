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
                INSERT INTO submissions (event_id, user_id, song_name, url, duration, submission_time, track_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (event_id, ctx.author.id, song_name, song_url, song_dur_sec, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), track_id))
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

            sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)

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
                if result:
                    milestone_reached = bool(result[0])
                else:
                    milestone_reached = False

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
        channel = self.bot.get_channel(channel_id)

        submissions = self.get_submissions(event_id)
        scores = {}
        for submission in submissions:
            score = self.calculate_score(submission[0])
            scores[submission[3]] = score

        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        top_10 = sorted_scores[:10]

        embed = discord.Embed(title=f"Event '{event[1]}' has ended!", description="Top 10 Results:")
        for song, score in top_10:
            embed.add_field(name=song, value=f"Score: {score}", inline=False)

        try:
            await channel.send(embed=embed)
            winners_channel_id = int(os.environ.get("WINNERS_CHANNEL_ID", 0))
            if winners_channel_id:
                winners_channel = self.bot.get_channel(winners_channel_id)
                await winners_channel.send(embed=embed)
        except Exception as e:
            logging.error(f"Failed to send results message: {e}")

        # Mark event as inactive
        cursor.execute("UPDATE events SET active = 0 WHERE event_id = ?", (event_id,))
        conn.commit()

        logging.info(f"Event {event_id} has ended and been marked inactive.")

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

def setup(bot):
    bot.add_cog(Commands(bot))