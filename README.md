# Discord Bot - Countdown

Manage COUNTDOWN song competition events in Discord!

Users submit songs within a set time period.  Members of the Discord server can then vote on their favorite submissions, and the bot tracks the scores, possibly announcing milestones along the way. At the end of the event's duration, the bot declares a winner based on the highest-scoring song. It's a fun, interactive way for users to share and discover music within a Discord community, centered around specific themes.

## Features

*   Create and manage countdown events with customizable durations.
*   Submit songs to active events.
*   Vote on song submissions (up to 3 votes per user per event).
*   Track milestones for submissions based on votes.
*   Announce event winners.
*   Store previous event standings.

## Commands

*   `/create <name> <duration> <min_submissions> <max_submissions> <song_min_duration> <song_max_duration>`: Creates a new countdown event.
*   `/submit <url>`: Submits a song to the active event.
*   `/vote <submission_id>`: Votes on a submission.
*   `/end`: Ends the current event.

## Dependencies

This project uses the following libraries:

*   `discord.py`
*   `PyNaCl`
*   `PyYAML`

These dependencies are listed in the `requirements.txt` file.

## Contributing

Feel free to submit pull requests or open issues to improve the bot.

## License

This project is licensed under the [MIT License](LICENSE) - see the LICENSE file for details. (You should create a LICENSE file and choose an appropriate license).
