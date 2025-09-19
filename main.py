#!/usr/bin/python
import os
import logging

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

def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    v = v.strip().lower()
    return v in ("1", "true", "t", "yes", "y", "on")


DISCORD_TOKEN = required_env("DISCORD_BOT_TOKEN")
INPUT_CHANNEL_ID = required_env("INPUT_CHANNEL_ID")
OUTPUT_CHANNEL_ID = required_env("OUTPUT_CHANNEL_ID")
#GUILD_ID = required_env("GUILD_ID")
SEND_RESULTS = _env_bool("SEND_RESULTS", default=False)


@bot.event
async def on_ready():
    logger.info("Bot is ready. Guilds: %s", [g.name for g in bot.guilds])
    input_channel = bot.get_channel(int(INPUT_CHANNEL_ID))
    output_channel = bot.get_channel(int(OUTPUT_CHANNEL_ID))
    await catchup(input_channel, user_dict, GAME)
    await print_stats(output_channel, user_dict, bot, GAME, SEND_RESULTS)
    await send_last_n_month_calendars(output_channel, user_dict, 4, use_emojis=False)

@bot.command()
async def game(ctx, arg=None):
    logger.info("!game invoked by %s in #%s", ctx.author, getattr(ctx.channel, "name", ctx.channel))
    await catchup(ctx.channel, user_dict, GAME)
    await print_stats(ctx.channel, user_dict, bot, GAME, SEND_RESULTS)


@bot.event
async def on_message(msg):
    if msg.author == bot.user:
        return
    # Only read/parse messages from Discord apps:
    # - bot accounts (author.bot)
    # - application/interactions (message.application_id)
    # - webhooks (message.webhook_id), including application-owned webhooks
    is_app_message = (
        getattr(getattr(msg, "author", None), "bot", False)
        or getattr(msg, "application_id", None) is not None
        or getattr(msg, "webhook_id", None) is not None
    )
    if is_app_message:
        logger.debug(
            "on_message(app): guild=%s channel=%s author=%s content='%s...'",
            getattr(getattr(msg, "guild", None), "name", None),
            getattr(getattr(msg, "channel", None), "name", None),
            getattr(getattr(msg, "author", None), "name", None),
            (getattr(msg, "content", "") or "")[:120]
        )
        count = await parse_result(msg, user_dict, GAME)
        if count:
            logger.info("on_message: ingested %s results from message id=%s", count, getattr(msg, "id", None))
    # Always let command handling proceed (so humans can use !commands)
    await bot.process_commands(msg)


bot.run(DISCORD_TOKEN)