import os
import logging
import asyncio
from datetime import datetime, timedelta
import json

import discord
from discord.ext import commands

from bot_setup import cursor, conn, time_to_seconds, get_active_event, DB_PATH

# File to store previous standings
PREVIOUS_STANDINGS_FILE = "previous_standings.json"

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
            
    @commands.command(name="submitvote")
    async def submitvote(self, ctx, *votes):
        """Submits votes to the active event (DM only)."""
        if not isinstance(ctx.channel, discord.DMChannel):
            await ctx.send("⚠️ This command can only be used in DMs.")
            return

        event = get_active_event()
        if not event:
            await ctx.author.send("⚠️ No active event found.")
            return

        event_id = event[0]
        event_name = event[1]

        # Check if user has already voted
        cursor.execute("SELECT COUNT(*) FROM votes WHERE user_id = ? AND submission_id IN (SELECT submission_id FROM submissions WHERE event_id = ?)", (ctx.author.id, event_id))
        vote_count = cursor.fetchone()[0]
        if vote_count > 0:
            await ctx.author.send("⚠️ You have already voted in this event.")
            return

        if len(votes) != 3:
            await ctx.author.send("⚠️ You must submit exactly 3 votes.")
            return

        vote_values = {0: 5, 1: 3, 2: 1}
        submission_ids = []
        for i, vote in enumerate(votes):
            try:
                track_number = int(vote)
                cursor.execute("SELECT submission_id FROM submissions WHERE event_id = ? AND track_id = ?", (event_id, f"Track-{track_number}"))
                submission = cursor.fetchone()
                if not submission:
                    await ctx.author.send(f"⚠️ Invalid track number: {track_number}")
                    return
                submission_id = submission[0]
                submission_ids.append(submission_id)
            except ValueError:
                await ctx.author.send(f"⚠️ Invalid track number format: {vote}")
                return

        # Store the votes
        for i, submission_id in enumerate(submission_ids):
            vote_value = vote_values[i]
            cursor.execute("INSERT INTO votes (submission_id, user_id, vote_value, vote_time, voter_name) VALUES (?, ?, ?, ?, ?)",
                           (submission_id, ctx.author.id, vote_value, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ctx.author.name))
        conn.commit()

        await self.update_event_message(event_id)
        await ctx.author.send(f"✅ Your votes for event '{event_name}' have been recorded!")

    @commands.command(name="charts")
    @commands.has_permissions(administrator=True)
    async def charts(self, ctx):
        """Displays the current leaderboard (Charts) for the active event (Admin only)."""
        event = get_active_event()
        if not event:
            await ctx.send("⚠️ No active event found.")
            return

        event_id = event[0]
        event_name = event[1]
        channel_id = event[9]

        leaderboard_msg = await self.generate_admin_leaderboard(event_id, event_name)
        await ctx.send(leaderboard_msg)
        await ctx.send("What would you like to do?\n\n1. Publish to [Public Channel Name]\n2. Exit")

        def check(msg):
            return msg.author == ctx.author and msg.channel == ctx.channel

        try:
            response_msg = await self.bot.wait_for("message", check=check, timeout=60)
            response = response_msg.content.lower()

            if response == "1":
                public_channel_id = int(os.environ.get("PUBLIC_CHANNEL_ID"))  # Replace with your actual channel ID environment variable
                if public_channel_id:
                    public_channel = self.bot.get_channel(public_channel_id)
                    await self.publish_public_charts(event_id, event_name, public_channel)
                    await ctx.send("Standings published to the public channel!")
                else:
                    await ctx.send("⚠️ Public channel ID not configured. Please set the PUBLIC_CHANNEL_ID environment variable.")
            elif response == "2":
                await ctx.send("Exiting command. Standings not published.")
            else:
                await ctx.send("Invalid response. Standings not published.")

        except asyncio.TimeoutError:
            await ctx.send("⚠️ No response received. Standings not published.")

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

    async def publish_public_charts(self, event_id, event_name, channel):
        """Publishes the public version of the charts to a designated channel, with arrows indicating rank changes."""
        current_standings = await self.generate_public_leaderboard(event_id, event_name)
        previous_standings = self.load_previous_standings()

        if previous_standings:
            updated_standings = self.compare_standings(previous_standings, current_standings)
        else:
            updated_standings = current_standings

        await channel.send(updated_standings)
        self.save_current_standings(current_standings)
        
    def load_previous_standings(self):
        """Loads the previous standings from a JSON file."""
        try:
            with open(PREVIOUS_STANDINGS_FILE, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return None

    def save_current_standings(self, standings):
        """Saves the current standings to a JSON file."""
        with open(PREVIOUS_STANDINGS_FILE, "w") as f:
            json.dump(standings, f)

    def compare_standings(self, previous, current):
        """Compares the current standings to the previous standings and adds up/down arrows."""
        # Extract rankings from the formatted strings
        prev_ranks = {line.split(".")[1].split("]")[0].strip(): rank for rank, line in enumerate(previous.split("\n")[2:] if line and "." in line)}
        curr_ranks = {line.split(".")[1].split("]")[0].strip(): rank for rank, line in enumerate(current.split("\n")[2:] if line and "." in line)}
    
        updated_lines = []
        for line in current.split("\n"):
            parts = line.split(".")
            if len(parts) > 1:
                song_name = parts[1].split("]")[0].strip()
                # Find the previous rank
                prev_rank = prev_ranks.get(song_name)
    
                # Determine the change in rank
                if prev_rank is not None:
                    curr_rank = curr_ranks[song_name]
                    if curr_rank < prev_rank:
                        change = "⬆️"  # Up arrow
                    elif curr_rank > prev_rank:
                        change = "⬇️"  # Down arrow
                    else:
                        change = ""  # No change
                else:
                    change = ""
    
                updated_lines.append(f"{line} {change}")
            else:
                updated_lines.append(line)
    
        return "\n".join(updated_lines)
    
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

            # Find the highest score
            highest_score = sorted_scores[0][1] if sorted_scores else 0
            cursor.execute("UPDATE events SET highest_score = ? WHERE event_id = ?", (highest_score, event_id))
            conn.commit()

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

        # Get the highest score from the database
        cursor.execute("SELECT highest_score FROM events WHERE event_id = ?", (event_id,))
        result = cursor.fetchone()
        highest_score = result[0] if result else 0

        # Calculate milestones based on the highest score
        milestones = [0.5, 0.75, 1.0]  # Example: 50%, 75%, and 100% of the highest score
        for milestone in milestones:
            target_score = highest_score * milestone

            if score >= target_score:
                cursor.execute("SELECT milestone_reached FROM submissions WHERE submission_id = ?", (submission_id,))
                result = cursor.fetchone()
                milestone_reached = bool(result[0]) if result else False

                if not milestone_reached:
                    try:
                        await channel.send(f"🎉 {song_name} has reached {int(milestone * 100)}% of the highest score with {score} points!")
                    except Exception as e:
                        logging.error(f"Failed to send milestone message: {e}")

                    cursor.execute("UPDATE submissions SET milestone_reached = ? WHERE submission_id = ?", (True, submission_id))
                    conn.commit()

    async def end_event(self, event_id):
        """Ends the event, displays the results, and provides options for publishing."""
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

        sorted_scores = sorted(scores.items(), key=lambda x: x[1][1], reverse=True)

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

        # Send results to admin channel and prompt for action
        admin_channel_id = int(os.environ.get("ADMIN_CHANNEL_ID", channel_id)) # You'll need to add an ADMIN_CHANNEL_ID env variable.
        admin_channel = self.bot.get_channel(admin_channel_id)

        if admin_channel:
            admin_results = await self.generate_admin_leaderboard(event_id, event[1])
            await admin_channel.send(admin_results)
            await admin_channel.send("Event has ended. What would you like to do?\n\n1. Publish final results to #general\n2. Countdown results from lowest to highest\n3. Exit and finish the event")

            def check(msg):
                return msg.channel == admin_channel and msg.author.guild_permissions.administrator

            try:
                response_msg = await self.bot.wait_for("message", check=check, timeout=120)
                response = response_msg.content.lower()

                if response == "1":
                    public_channel_id = int(os.environ.get("PUBLIC_CHANNEL_ID", channel_id)) # Use event channel as default
                    public_channel = self.bot.get_channel(public_channel_id)
                    if public_channel:
                        public_results = await self.generate_public_leaderboard(event_id, event[1])
                        await public_channel.send(public_results)
                        await admin_channel.send("Final results published to the public channel!")
                    else:
                        await admin_channel.send("⚠️ Public channel ID not configured. Could not publish results.")

                elif response == "2":
                    await admin_channel.send("Counting down results...")
                    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=False)  # Sort ascending for countdown
                    for rank, (song, score) in enumerate(sorted_scores, 1):
                        await channel.send(f"{len(sorted_scores) - rank + 1}. {song} - **{score}** points")
                        await asyncio.sleep(5)  # 5-second delay between announcements

                    await admin_channel.send("Countdown complete!")

                elif response == "3":
                    await admin_channel.send("Exiting and finishing the event.")

                else:
                    await admin_channel.send("Invalid response. Event finished without further action.")

            except asyncio.TimeoutError:
                await admin_channel.send("⚠️ No response received. Event finished without further action.")

        # Mark event as inactive
        cursor.execute("UPDATE events SET active = 0 WHERE event_id = ?", (event_id,))
        conn.commit()

        # Clear previous standings
        self.save_current_standings("")

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