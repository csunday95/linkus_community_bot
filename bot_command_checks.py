
from discord.ext.commands import Context
from discord import Guild


def is_guild_owner(ctx: Context):
    """
    Returns True if the invoking user is the owner of the guild in which the command was invoked, False otherwise

    :param ctx: check execution context
    """
    guild = ctx.guild  # type: Guild
    return guild.owner == ctx.author
