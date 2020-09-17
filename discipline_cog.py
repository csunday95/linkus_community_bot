
from typing import Union
from discord import Guild, User, Member, AuditLogAction, NotFound
from discord.ext.commands import Cog, Context, Bot
from discord.ext import commands
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

    async def get_discipline_type_id(self, type_name):  # cache this for now; maybe clear cache later?
        ban_type, err = await self._backend_client.discipline_type_get_by_name(type_name)
        if ban_type is None:
            return None, err
        return ban_type['id'], None

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
        ban_type_id, err = await self.get_discipline_type_id(BAN_DISCIPLINE_TYPE_NAME)
        if ban_type_id is None:
            return f'unable to retrieve type ID for ban discipline: {err}'
        return await self._backend_client.discipline_event_create(
            user.id,
            user.display_name,
            mod_user_id,
            ban_type_id,
            ban_reason,
            ban_end_time
        )

    async def _resolve_user(self, candidate_guild: Guild, user_identifier: str, database_fallback: bool = False):
        try:
            user_snowflake = int(user_identifier)
            user_obj = candidate_guild.get_member(user_snowflake)
            if user_obj is None:
                # fall back to getting user generally
                user_obj = self.bot.get_user(user_snowflake)
        except ValueError:
            # if not an int, definitely not a snowflake, try to resolve by username
            user_obj = candidate_guild.get_member_named(user_identifier)
        if user_obj is None:
            if database_fallback:
                latest_event, err = await self._backend_client.discipline_event_get_latest_by_username(
                    username=user_identifier
                )
                if latest_event is not None:
                    try:
                        return await self.bot.fetch_user(latest_event['discord_user_snowflake']), None
                    except NotFound:
                        pass
            error_message = f'User {user_identifier} does not exist or is not currently a Member!'
            return None, error_message
        return user_obj, None

    async def _is_user_banned(self, user_snowflake: int, user_identifier: str):
        latest_ban, err = await self._backend_client.discipline_event_get_latest_ban(user_snowflake)
        if err is not None:
            return None, err
        if len(latest_ban) == 0:
            msg = f'user {user_identifier} is not currently banned.'
            return None, msg
        if latest_ban['is_pardoned']:
            msg = f'user {user_identifier} has had their ban pardoned.'
            return None, msg
        if latest_ban['is_terminated']:
            msg = f'user {user_identifier} was tempbanned, but the ban expired.'
            return None, msg
        return latest_ban, None

    @commands.command()
    async def ban(self, ctx: Context, user_identifier: str, *reason: str):
        await self.tempban(ctx, user_identifier, None, *reason)

    @commands.command()
    async def unban(self, ctx: Context, user_identifier: str, *reason: str):
        """pardon a currently active ban/tempban for a user"""
        if len(reason) == 0:
            reason = 'unbanned by command'
        else:
            reason = ' '.join(reason)
        user_obj, err = await self._resolve_user(ctx.guild, user_identifier, database_fallback=True)
        if user_obj is None:
            ctx.channel.send(f'<@!{ctx.author.id}> {err}')
            return
        target_guild = ctx.guild
        latest_ban, not_banned_reason = await self._is_user_banned(user_obj.id, user_identifier)
        if latest_ban is None:  # if the database says they aren't banned
            try:
                await target_guild.fetch_ban(user_obj)
                await target_guild.unban(user_obj, reason)
                fmt = 'User was unbanned, but a database inconsistency was discovered: {}'
                not_banned_reason = fmt.format(not_banned_reason)
            except NotFound:
                pass
            await ctx.channel.send(f'<@!{ctx.author.id}> {not_banned_reason}')
            return
        err = await self._backend_client.discipline_event_set_pardoned(latest_ban['id'], True)
        if err is not None:
            fmt = '<@!{}> Unable to pardon user {}, user remains banned: {}'
            await ctx.channel.send(fmt.format(ctx.author.id, user_identifier, err))
            return
        await target_guild.unban(user_obj, reason=reason)
        await ctx.channel.send(f'<@!{ctx.author.id}> User {user_identifier} has been unbanned.')

    @commands.command()
    async def tempban(self, ctx: Context, user_identifier: str, duration: Optional[str], *reason: str):
        if len(reason) == 0:
            reason = 'general ban'
        else:
            reason = ' '.join(reason)
        user_obj, err = await self._resolve_user(ctx.guild, user_identifier)
        if user_obj is None:
            ctx.channel.send(f'<@!{ctx.author.id}> {err}')
            return
        end_datetime = None
        if duration is None:
            commit_err = await self._commit_user_banned(ctx.author.id, user_obj, reason)
        else:
            duration_seconds = timeparse(duration)
            if duration_seconds is None:
                ctx.channel.send(f'<@!{ctx.author.id}> {duration} is not a valid duration representation!')
                return
            duration_delta = timedelta(seconds=duration_seconds)
            end_datetime = datetime.now() + duration_delta
            commit_err = await self._commit_user_banned(ctx.author.id, user_obj, reason, end_datetime)
        if commit_err is None:
            await ctx.guild.ban(user_obj, reason=reason)
            if duration is None:
                fmt = '<@!{author}> User {user} was permanently banned and the ban has been logged.'
            else:
                fmt = '<@!{author}> User {user} was banned until {duration} and the ban has been logged.'
            await ctx.channel.send(fmt.format(
                author=ctx.author.id,
                user=user_identifier,
                duration=end_datetime
            ))
        else:
            fmt = '<@!{}> User {} was not banned as a database entry could not be created: {}'
            await ctx.channel.send(fmt.format(ctx.author.id, user_identifier, commit_err))
