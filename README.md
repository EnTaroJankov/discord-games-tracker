# discord-games-tracker

A Discord bot for aggregating game results posted in text channels and presenting per-user and aggregate statistics. It includes a Wordle reference implementation and a generic core designed to support other games.

## Features

- Pluggable game architecture (generic core + per-game plugin)
- Robust message parsing with fallback for plain-text `@handles`
- Generic result model using `score` (works across games)
- Wordle-specific stats and visuals:
  - Per-user leaderboard with totals, streaks, and averages
  - Lifetime, 30-day, and 7-day average (numeric scores only; excludes 'X')
- Calendar visualizations:
  - Send side-by-side calendars of the last N months (N ≤ 12)
  - One Discord message per user (optional delay, user filtering)
  - Emoji or ASCII rendering (ASCII recommended for perfect alignment)
  - Unique colors for Wordle outcomes:
    - 1 → 🟩, 2 → 🟦, 3 → 🟨, 4 → 🟧, 5 → 🟥, 6 → 🟫, X → 🟪
    - Missed days are ⬛, future days are blank

## Requirements

- Python 3.10+
- Discord bot token
- Intents: `Message Content`, `Guilds`, `Members` (enable in the Bot settings)
- Dependencies (see `requirements.txt`):
  - `discord.py==2.6.3`
  - `APScheduler==3.11.0`
  - `python-dotenv`

Install dependencies:

## Setup

Set these environment variables in a `.env` file in the root directory:

```
DISCORD_BOT_TOKEN=<SECRET>
CHANNEL_ID=<SECRET>
LOG_LEVEL=INFO
SEND_RESULTS=False
```

Install dependencies (set up a virtual environment first)
```
pip install -r requirements.txt
```


run script with `python main.py`


If you want to create your own bot account:

[Create a bot account](https://discordpy.readthedocs.io/en/stable/discord.html)
Add permissions to read messages and enable the `message_content` intent.


Otherwise, you can use the bot account token in the repository secrets 


