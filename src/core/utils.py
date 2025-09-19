import logging

from discord.ext.commands import Bot

logger = logging.getLogger(__name__)

# List member visible in the input channel with multiple identity forms
async def print_member(bot: Bot, guild_id, user_id):
    guild = await bot.fetch_guild(guild_id)
    member = await guild.fetch_member(user_id)
    user = await bot.fetch_user(member.id)
    print("user.global_name=", getattr(user, "global_name"))
    print("nick=", member.nick, "display_name=", member.display_name)
    print("global_name=", member)
    print("name=", member.name)
    print("discriminator=", member.discriminator)
    print("id=", member.id)
    print("mention=", member.mention)
    print("user.name=", user.name)
    print("user.id=", user.id)
    print("user.discriminator=", user.discriminator)
    print("user.global_name=", getattr(user, "global_name"))
