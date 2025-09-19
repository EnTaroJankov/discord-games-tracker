#!/usr/bin/python
import os
import logging
from datetime import timezone, datetime
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands
from dotenv import load_dotenv
from src.core.runtime import print_stats, catchup, parse_result, send_last_n_month_calendars

load_dotenv()

CMD_PREFIX = '!'

user_dict = {}

# Logging setup
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

intents = discord.Intents(messages=True, message_content=True, guilds=True, members=True)
bot = commands.Bot(command_prefix=CMD_PREFIX, intents=intents)

# Inject the game plugin (Wordle reference implementation lives under examples/)
from src.examples.wordle.game import WordleGame
GAME = WordleGame()

def required_env(name: str) -> str:
    v = os.environ.get(name)
    if v is None or v == "":
        raise RuntimeError(f"Missing required env var: {name}")
    return v


DISCORD_TOKEN = required_env("DISCORD_BOT_TOKEN")
CHANNEL_ID = required_env("CHANNEL_ID")
SEND_RESULTS = required_env("SEND_RESULTS")


@bot.event
async def on_ready():
    logger.info("Bot is ready. Guilds: %s", [g.name for g in bot.guilds])
    channel = bot.get_channel(int(CHANNEL_ID))
    await catchup(channel, user_dict, GAME)
    await print_stats(channel, user_dict, bot, GAME, bool(SEND_RESULTS))
    pacific = ZoneInfo("America/Los_Angeles")
    now_pacific = datetime.now(pacific)
    utc_now = datetime.now(timezone.utc)
    utc_now_in_pacific = utc_now.astimezone(pacific)
    await send_last_n_month_calendars(channel, user_dict, 4, tz=pacific, use_emojis=False)

@bot.command()
async def game(ctx, arg=None):
    logger.info("!game invoked by %s in #%s", ctx.author, getattr(ctx.channel, "name", ctx.channel))
    await catchup(ctx.channel, user_dict, GAME)
    await print_stats(ctx.channel, user_dict, bot, GAME, bool(SEND_RESULTS))


@bot.event
async def on_message(msg):
    if msg.author == bot.user:
        return
    logger.debug(
        "on_message: guild=%s channel=%s author=%s content='%s...'",
        getattr(getattr(msg, "guild", None), "name", None),
        getattr(getattr(msg, "channel", None), "name", None),
        getattr(getattr(msg, "author", None), "name", None),
        (getattr(msg, "content", "") or "")[:120]
    )
    count = await parse_result(msg, user_dict, GAME)
    if count:
        logger.info("on_message: ingested %s results from message id=%s", count, getattr(msg, "id", None))
    await bot.process_commands(msg)


bot.run(DISCORD_TOKEN)