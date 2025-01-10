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