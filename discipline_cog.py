
from typing import Union
from discord import Guild, User, Member, Object
from discord.ext.commands import Cog, Context, Bot
from discord.ext import commands


class DisciplineCog(Cog, name='Discipline'):

    def __init__(self, bot: Bot):
        self.bot = bot

    @commands.Cog.listener()
    def on_member_ban(self, guild: Guild, user: Union[User, Member]):
        pass

    async def _handle_user_banned(self, user_snowflake: str):
        pass

    @commands.command()
    async def ban(self, ctx: Context, user_identifier: str, reason: str):
        target_guild = ctx.guild  # type: Guild
        try:
            user_snowflake = int(user_identifier)
            user_obj = Object(user_snowflake)
        except ValueError:
            # if not an int, definitely not a snowflake, try to resolve by username
            user_obj = target_guild.get_member_named(user_identifier)
        await target_guild.ban(user_obj, reason=reason)
