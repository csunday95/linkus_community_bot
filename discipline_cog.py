
from typing import Union
from discord import Guild, User, Member, AuditLogAction
from discord.ext.commands import Cog, Context, Bot
from discord.ext import commands
from async_lru import alru_cache
from datetime import datetime, timedelta
from pytimeparse.timeparse import timeparse
from bot_backend_client import *

BAN_DISCIPLINE_TYPE_NAME = 'ban'

# https://discord.com/api/oauth2/authorize?client_id=754719676541698150&scope=bot&permissions=268921926


class DisciplineCog(Cog, name='Discipline'):

    def __init__(self, bot: Bot, backend_client: BotBackendClient):
        self.bot = bot
        self._backend_client = backend_client
        self._audit_log_cache = []
        self._audit_log_last_seen = None

    @alru_cache()
    async def get_discipline_type_id(self, type_name):  # cache this for now; maybe clear cache later?
        ban_type_id = await self._backend_client.discipline_type_get_by_name(type_name)
        if ban_type_id is None:
            return None
        return ban_type_id

    @commands.Cog.listener()
    async def on_member_ban(self, guild: Guild, user: Union[User, Member]):
        initiating_user, ban_reason = None, None
        banned_user = user
        # linearly search bans in audit log for this one
        async for ban_entry in guild.audit_logs(action=AuditLogAction.ban):
            banned_user = ban_entry.target  # type: Optional[User]
            if banned_user != user:
                continue
            initiating_user = ban_entry.user  # type: Optional[User]
            if initiating_user == self.bot.user.id:
                return  # this was a bot ban, don't need to do anything else
            ban_reason = ban_entry.reason
            break
        # if we were unable to find the audit log entry, fallback to fetching ban entry
        if ban_reason is None:
            ban_entry = await guild.fetch_ban(user)
            if ban_entry is None:
                return  # TODO: handle error
            ban_reason = ban_entry.reason
        if initiating_user is None:
            initiating_user_id = 0  # fall back to zero if ban isn't found in audit log
        else:
            initiating_user_id = initiating_user.id
        # create database entry if this is not bot initiated
        if initiating_user_id != self.bot.user.id:
            await self._commit_user_banned(initiating_user_id, banned_user, ban_reason)

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'ready: {self.bot.user.id}')

    async def _commit_user_banned(self, mod_user_id: int, user: User, ban_reason: str, ban_end_time: datetime = None):
        ban_type_id = await self.get_discipline_type_id(BAN_DISCIPLINE_TYPE_NAME)
        success = await self._backend_client.discipline_event_create(
            user.id,
            user.display_name,
            mod_user_id,
            ban_type_id,
            ban_reason,
            ban_end_time
        )
        if not success:
            return  # TODO: handle error

    async def _resolve_user(self, guild: Guild, user_identifier: str):
        try:
            user_snowflake = int(user_identifier)
            user_obj = guild.get_member(user_snowflake)
            if user_obj is None:
                # fall back to getting user generally
                user_obj = self.bot.get_user(user_snowflake)
        except ValueError:
            # if not an int, definitely not a snowflake, try to resolve by username
            user_obj = guild.get_member_named(user_identifier)
        return user_obj

    @commands.command()
    async def test_command(self, ctx: Context):
        await self._backend_client.discipline_type_get_by_name('ban')

    @commands.command()
    async def ban(self, ctx: Context, user_identifier: str, *reason: str):
        await self.tempban(ctx, user_identifier, None, *reason)

    @commands.command()
    async def unban(self, ctx: Context, user_identifier: str):
        pass

    @commands.command()
    async def tempban(self, ctx: Context, user_identifier: str, duration: Optional[str], *reason: str):
        if len(reason) == 0:
            reason = 'general ban'
        else:
            reason = ' '.join(reason)
        target_guild = ctx.guild  # type: Guild
        user_obj = await self._resolve_user(target_guild, user_identifier)
        if user_obj is None:
            error_message = f'<@!{ctx.author.id}> User {user_identifier} does not exist or is not currently a Member!'
            await ctx.channel.send(error_message)
            return
        await target_guild.ban(user_obj, reason=reason)
        if duration is None:
            await self._commit_user_banned(ctx.author.id, user_obj, reason)
        else:
            duration_seconds = timeparse(duration)
            duration_delta = timedelta(seconds=duration_seconds)
            end_datetime = datetime.now() + duration_delta
            await self._commit_user_banned(ctx.author.id, user_obj, reason, end_datetime)
