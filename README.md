# discord-games-tracker
discord bot for aggregating statistics from games that post their results in text channels

## Setup

Set these environment variables in a `.env` file in the src directory:

`DISCORD_BOT_TOKEN`: your discord bot's token
`CHANNEL_ID`: channel ID of the channel to track
`GUILD_ID`: guild ID of the server to track (aka server id)


[Create a bot account](https://discordpy.readthedocs.io/en/stable/discord.html)
Add permissions to read messages and enable the `message_content` intent.