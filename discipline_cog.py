
from typing import Union, Tuple, Awaitable
from discord import Guild, User, Member, AuditLogAction, NotFound, Object, Role
from discord.ext.commands import Cog, Context, Bot
from discord.ext import commands
from datetime import timedelta
from pytimeparse.timeparse import timeparse
from bot_backend_client import *

BAN_DISCIPLINE_TYPE_NAME = 'ban'
ADD_ROLE_DISCIPLINE_TYPE_NAME = 'add_role'
MUTE_DISCORD_ROLE_NAME = 'muted'

# https://discord.com/api/oauth2/authorize?client_id=754719676541698150&scope=bot&permissions=268921926


class DisciplineCog(Cog, name='Discipline'):

    def __init__(self, bot: Bot, backend_client: BotBackendClient):
        self.bot = bot
        self._backend_client = backend_client
        self._audit_log_cache = []
        self._audit_log_last_seen = None

    async def get_discipline_type_id(self, type_name: str) -> Tuple[Optional[int], Optional[str]]:
        """
        Pulls the database id of the discipline type matching the given name

        :param type_name:
        :return: A tuple of (int, None) with the type ID on success, (None, error) message on failure
        """
        ban_type, err = await self._backend_client.discipline_type_get_by_name(type_name)
        if ban_type is None:
            return None, err
        return ban_type['id'], None

    @commands.Cog.listener()
    async def on_member_ban(self, guild: Guild, user: Union[User, Member]):
        """
        handler for member ban events; checks if this was a bot ban, and if not (ban was made by a mod in the UI), then
        a ban entry is created with presumed perma-ban duration.

        :param guild: the guild within which the ban occurred
        :param user: the user being banned
        """
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
            await self._commit_user_discipline(
                initiating_user_id,
                banned_user,
                BAN_DISCIPLINE_TYPE_NAME,
                ban_reason
            )

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'ready: {self.bot.user.id}')

    async def _commit_user_discipline(self,
                                      mod_user_id: int,
                                      user: Union[User, Member],
                                      discipline_type_name: str,
                                      reason: str,
                                      discipline_end_time: datetime = None) -> Optional[str]:
        """
        Creates a DisciplineEvent entry in the database via the API.

        :param mod_user_id: The snowflake of the moderating user
        :param user: the user being disciplined as a User or Member object
        :param discipline_type_name: the name of the discipline type being applied
        :param reason: the reason for this discipline
        :param discipline_end_time: the end time/date of this discipline, or None if indefinite
        :return: None on success, an error message if failed
        """
        # extract the discipline database ID by name
        discipline_type_id, err = await self.get_discipline_type_id(discipline_type_name)
        if discipline_type_id is None:
            return f'unable to retrieve type ID for discipline type {discipline_type_name}: {err}'
        # create database entry via API endpoint
        return await self._backend_client.discipline_event_create(
            user.id,
            str(user),
            mod_user_id,
            discipline_type_id,
            reason,
            discipline_end_time
        )

    @staticmethod
    def _combine_reason(reason_list: Tuple[str], default: str):
        """
        Combines the final argument reason argument into a single string. If empty, returns the given default value.

        :param reason_list: The list of strings to join
        :param default: the default value to return if the list is empty
        :return: the combined reason string or the default value as required
        """
        if len(reason_list) == 0:
            reason = default
        else:
            reason = ' '.join(reason_list)
        return reason

    async def _resolve_user(self, candidate_guild: Guild, user_identifier: str, database_fallback: bool = False) -> \
            Tuple[Optional[User], Optional[str]]:
        """
        Attempts to resolve the given user identifier string to a user or member object within the given Guild.

        If an integer value is given, this function will assume the identifier is

        :param candidate_guild:
        :param user_identifier:
        :param database_fallback:
        :return:
        """
        # first, try getting by username
        try:
            user_obj = candidate_guild.get_member_named(user_identifier)
        except NotFound:
            user_obj = None
        # if username not a member, try getting as a snowflake
        if user_obj is None:
            try:
                user_snowflake = int(user_identifier)
                user_obj = candidate_guild.get_member(user_snowflake)
                if user_obj is None:
                    # fall back to getting user generally
                    user_obj = self.bot.get_user(user_snowflake)
            except ValueError:
                pass
        # if we were unable to resolve a user/member from given identifer
        if user_obj is None:
            # if database_fallback was specified, see if user has been disciplined, and has a discipline event entry
            if database_fallback:
                latest_event, err = await self._backend_client.discipline_event_get_latest_by_username(
                    username=user_identifier
                )
                # if an event exists for the username, extract the snowflake from that
                if latest_event is not None:
                    try:
                        return await self.bot.fetch_user(latest_event['discord_user_snowflake']), None
                    except NotFound:
                        pass
            error_message = f'User {user_identifier} does not exist or is not currently a Member!'
            return None, error_message
        return user_obj, None

    @staticmethod
    async def _resolve_member(candidate_guild: Guild, user_identifier: str) -> Tuple[Optional[Member], Optional[str]]:
        """
        Attempts to resolve a member object from the given user identifier. First attempts to resolve by username, then
        attempts to resolve as if user_identifier is a snowflake.

        :param candidate_guild: the guild to search for the given user in
        :param user_identifier: the identifier to attempt to resolve from
        :return: Returns a tuple of (Member, None) on success, (None, Error Message) on failure
        """
        try:
            user_obj = candidate_guild.get_member_named(user_identifier)
        except NotFound:
            user_obj = None
        try:
            user_snowflake = int(user_identifier)
            user_obj = candidate_guild.get_member(user_snowflake)
        except ValueError:
            pass
        if user_obj is None:
            return None, f'User {user_identifier} is not currently a Member!'
        return user_obj, None

    @staticmethod
    async def _resolve_role(target_guild: Guild, role_name: str) -> Tuple[Optional[Role], Optional[str]]:
        """
        Attempts to resolve a Role object from the given guild that matches the provided name. Matching is
        case insensitive, but must be exact.

        :param target_guild: The guild to find the role within
        :param role_name: the name of the role to search for
        :return: a tuple of (Role, warning message or None) on success, or (None, error message) on failure.
        """
        guild_roles = target_guild.roles
        matching_roles = list(filter(lambda r: r.name.lower() == role_name, guild_roles))
        if len(matching_roles) == 0:
            # fall back to getting role by snowflake if possible
            try:
                role_id = int(role_name)
                matching_roles = [await target_guild.get_role(role_id)]
            except (ValueError, TypeError, NotFound):
                msg = f'No role matching name "{role_name}" exists!'
                return None, msg
        if len(matching_roles) > 1:
            warning_msg = f'Warning, multiple matches found for role "{role_name}"!'
        else:
            warning_msg = None
        matched_role = matching_roles[0]
        return matched_role, warning_msg

    async def _is_user_disciplined(self, user_object: Union[User, Member], discipline_type_name: str) \
            -> Tuple[Optional[dict], Optional[str]]:
        """
        Checks if the given user has an active discipline of the given type according the the database.

        :param user_object: The user object to check for discipline status of
        :param discipline_type_name: the discipline type to filter by
        :return: A tuple of (discipline event dict, None) on success, (None, error message) on failure
        """
        latest_discipline, err = await self._backend_client.discipline_event_get_latest_discipline_of_type(
            user_object.id,
            discipline_type_name
        )
        if err is not None:
            return None, err
        username, disc, user_id = user_object.name, user_object.discriminator, user_object.id
        # if user has never received a discipline of this type
        if len(latest_discipline) == 0:
            msg = f'User {username}#{disc} [{user_id}] has not been disciplined with type {discipline_type_name}.'
            return None, msg
        # if the most recent discipline is pardoned
        if latest_discipline['is_pardoned']:
            msg = f'User {username}#{disc} [{user_id}] has had their latest' \
                  f' discipline of type {discipline_type_name} pardoned.'
            return None, msg
        # if the most recent discipline expired and was terminated
        if latest_discipline['is_terminated']:
            msg = f'User {username}#{disc} [{user_id}] had temporary' \
                  f' discipline of type {discipline_type_name}, but it expired.'
            return None, msg
        return latest_discipline, None

    async def _apply_discipline(self,
                                ctx: Context,
                                user_object: Union[User, Member],
                                discipline_type_name: str,
                                duration: Optional[str],
                                reason: str,
                                discord_discipline_coroutine: Optional[Awaitable]):
        """
        Apply the indicated discipline type to the given user for the given duration. This consists of creating a
        discipline event entry on the database and running the discord discipline coroutine.

        :param ctx: the discord bot context to execute with
        :param user_object: the user object to discipline
        :param discipline_type_name: the name of the discipline type to apply
        :param duration: the duration of the discipline, or None if indefinite
        :param reason: the reason for this discipline event
        :param discord_discipline_coroutine: the discord related coroutine to carry out in order to enact the discipline
        within discord.
        """
        end_datetime = None
        # create database entry
        if duration is None:
            commit_err = await self._commit_user_discipline(
                ctx.author.id,
                user_object,
                discipline_type_name,
                reason
            )
        else:
            # if duration is not none, compute discipline end date/time
            duration_seconds = timeparse(duration)
            if duration_seconds is None:
                await ctx.channel.send(f'<@!{ctx.author.id}> {duration} is not a valid duration representation!')
                return
            duration_delta = timedelta(seconds=duration_seconds)
            end_datetime = datetime.now() + duration_delta
            commit_err = await self._commit_user_discipline(
                ctx.author.id,
                user_object,
                discipline_type_name,
                reason,
                end_datetime
            )
        full_username = str(user_object)
        if commit_err is None:
            # await given discord discipline coroutine to carry out discipline discord-side
            if discord_discipline_coroutine is not None:
                await discord_discipline_coroutine
            # send feedback message to moderator
            if duration is None:
                fmt = '<@!{author}> User {user} [{user_id}] had discipline {discipline_type} permanently' \
                      ' applied and the action has been logged.'
            else:
                fmt = '<@!{author}> User {user} [{user_id}] had discipline {discipline_type} applied until {duration}' \
                      ' and the action has been logged.'
            await ctx.channel.send(fmt.format(
                author=ctx.author.id,
                user=full_username,
                user_id=user_object.id,
                duration=end_datetime,
                discipline_type=discipline_type_name
            ))
        else:
            # indicate we could not carry out database event creation
            fmt = '<@!{}> User {} [{}] was not disciplined as a database entry could not be created: {}'
            await ctx.channel.send(
                fmt.format(ctx.author.id, full_username, user_object.id, commit_err)
            )

    async def _pardon_discipline(self,
                                 ctx: Context,
                                 user_object: Union[User, Member],
                                 discipline_type_name: str,
                                 discord_pardon_coroutine: Awaitable) -> None:
        """
        Pardons latest discipline of a current type if possible. The most recent discipline will be pardoned if
        it is not already pardoned or expired.

        :param ctx: the context work within
        :param user_object: the user to pardon
        :param discipline_type_name: the name of the discipline type to filter by
        :param discord_pardon_coroutine: the pardoning coroutine to realize the pardon on discord side
        """
        latest_discipline, not_disc_reason = await self._is_user_disciplined(
            user_object, discipline_type_name
        )
        if latest_discipline is None:  # if the database says they aren't disciplined
            msg = f'<@!{ctx.author.id}> No record exists for this user being disciplined: {not_disc_reason}'
            await ctx.channel.send(msg)
            return
        err = await self._backend_client.discipline_event_set_pardoned(latest_discipline['id'], True)
        full_username = str(user_object)
        if err is not None:
            fmt = '<@!{}> Unable to pardon user {} [{}], user remains banned: {}'
            await ctx.channel.send(fmt.format(ctx.author.id, full_username, user_object.id, err))
            return
        await discord_pardon_coroutine
        msg = f'<@!{ctx.author.id}> User {full_username} [{user_object.id}] has ' \
              f'had latest discipline of type {discipline_type_name} pardoned.'
        await ctx.channel.send(msg)

    @commands.command()
    async def ban(self, ctx: Context, user_identifier: str, *reason: str) -> None:
        """
        Carry out an indefinite ban for the given user.

        :param ctx: the context to work within
        :param user_identifier: the user to ban
        :param reason: the reason for the ban
        """
        # just treat as a permanent temp ban
        await self.tempban(ctx, user_identifier, None, *reason)

    @commands.command()
    async def tempban(self, ctx: Context, user_identifier: str, duration: Optional[str], *reason: str) -> None:
        """
        Temporarily ban the given user. The duration is specified as a string like "1h30m"

        :param ctx: the context to work within
        :param user_identifier: the user to temporarily ban
        :param duration: the duration to ban the user for, or None for indefinite ban
        :param reason: the reason the user is being banned
        """
        reason = self._combine_reason(reason, 'general ban')
        user_obj, err = await self._resolve_user(ctx.guild, user_identifier, database_fallback=True)
        if user_obj is None:
            await ctx.channel.send(f'<@!{ctx.author.id}> {err}')
            return
        await self._apply_discipline(
            ctx,
            user_obj,
            BAN_DISCIPLINE_TYPE_NAME,
            duration,
            reason,
            ctx.guild.ban(user_obj, reason=reason)
        )

    @commands.command()
    async def unban(self, ctx: Context, user_identifier: str, *reason: str):
        """
        Removes a ban from the given user with the supplied reason.

        :param ctx: the context to work within
        :param user_identifier:
        :param reason:
        :return:
        """
        reason = self._combine_reason(reason, 'general unban')
        user_obj, err = await self._resolve_user(ctx.guild, user_identifier, database_fallback=True)
        if user_obj is None:
            await ctx.channel.send(f'<@!{ctx.author.id}> {err}')
            return
        await self._pardon_discipline(
            ctx, user_obj, BAN_DISCIPLINE_TYPE_NAME, ctx.guild.unban(user_obj, reason=reason)
        )

    @commands.command()
    async def add_role(self, ctx: Context, user_identifier: str, role_name: str, *reason: str) -> None:
        """
        Adds the discord role with the matching name to the given user.

        :param ctx: the context to work within
        :param user_identifier: the user to add the role to
        :param role_name: the name of the role to add
        :param reason: the reason this role was added
        """
        await self.temp_add_role(ctx, user_identifier, role_name, None, *reason)

    async def _prepare_role_changes(self, ctx: Context, user_identifier: str, role_name: str)\
            -> Tuple[Optional[Member], Optional[Role]]:
        """
        Performs the necessary steps to retrieve user and role objects from a guild. Will send messages in the channel
        if an error occurs and (None, None) will be returned.

        :param ctx: the context to work within
        :param user_identifier: the user to add the role to
        :param role_name: the name of the role being changed
        :return: A tuple of (Member Object, Role Object) on success, (None, None) on failure.
        """
        member_obj, err = await self._resolve_member(ctx.guild, user_identifier)
        if member_obj is None:
            await ctx.channel.send(f'<@!{ctx.author.id}> Unable to add role: {err}')
            return None, None
        matched_role, msg = await self._resolve_role(ctx.guild, role_name)
        if matched_role is None:
            # if we got an error, send message and exit
            ctx.channel.send(f'<@!{ctx.author.id}> Unable to find role: {msg}')
            return None, None
        elif msg is not None:
            # if we got a warning, issue warning and continue
            ctx.channel.send(f'<@!{ctx.author.id}> {msg}')
        return member_obj, matched_role

    @commands.command()
    async def temp_add_role(self,
                            ctx: Context,
                            user_identifier: str,
                            role_name: str,
                            duration: Optional[str],
                            *reason: str) -> None:
        """
        Temporarily add the given role to the given user. Role must already exist and is matched by name

        :param ctx: the context to operate within
        :param user_identifier: the user to add the role to
        :param role_name: the role to add by name or by snowflake
        :param duration: the duration to apply the role for, or None for indefinite
        :param reason: the reason the role is being applied
        """
        if len(reason) == 0:
            reason = 'no reason provided'
        else:
            reason = ' '.join(reason)
        member_obj, matched_role = await self._prepare_role_changes(ctx, user_identifier, role_name)
        if member_obj is None or matched_role is None:
            return
        if matched_role in member_obj.roles:
            full_username, member_id = str(member_obj), member_obj.id
            await ctx.channel.send(
                f'<@!{ctx.author.id}> User {full_username} [{member_id}] already has role with name "{role_name}"!'
            )
            return
        await self._apply_discipline(
            ctx,
            member_obj,
            ADD_ROLE_DISCIPLINE_TYPE_NAME,
            duration,
            reason,
            member_obj.add_roles(matched_role, reason=reason)
        )

    @commands.command()
    async def remove_role(self, ctx: Context, user_identifier: str, role_name: str, *reason: str) -> None:
        """
        Remove the role with the matching name from the given user.

        :param ctx: the discord bot context to operate in
        :param user_identifier: the user to mute indefinitely
        :param role_name: the name of the role to remove
        :param reason: the reason this role was removed
        :return:
        """
        if len(reason) == 0:
            reason = 'no reason provided'
        else:
            reason = ' '.join(reason)
        member_obj, matched_role = await self._prepare_role_changes(ctx, user_identifier, role_name)
        if member_obj is None or matched_role is None:
            return
        await self._pardon_discipline(
            ctx,
            member_obj,
            ADD_ROLE_DISCIPLINE_TYPE_NAME,
            await member_obj.remove_roles(matched_role, reason=reason)
        )

    @commands.command()
    async def mute(self, ctx: Context, user_identifier: str, *reason: str) -> None:
        """
        Applies the configured mute role to the given user for the given reason indefinitely.

        :param ctx: the discord bot context to operate in
        :param user_identifier: the user to mute indefinitely
        :param reason: the reason for the mute
        """
        await self.tempmute(ctx, user_identifier, None, *reason)

    @commands.command()
    async def tempmute(self, ctx: Context, user_identifier: str, duration: Optional[str], *reason: str) -> None:
        """
        Temporarily adds the configured mute role to the given user for the given reason.

        :param ctx: the discord bot context to operate in
        :param user_identifier: the user to mute
        :param duration: the duration the mute should hold for
        :param reason: the reason this user is being muted
        """
        await self.temp_add_role(ctx, user_identifier, MUTE_DISCORD_ROLE_NAME, duration, *reason)

    @commands.command()
    async def unmute(self, ctx: Context, user_identifier: str, *reason: str) -> None:
        """
        Removes the configured mute role from the given user.

        :param ctx: the discord bot context to operate in
        :param user_identifier: the user to remove the mute role from
        :param reason: the reason for the removal of the mute role
        """
        await self.remove_role(ctx, user_identifier, MUTE_DISCORD_ROLE_NAME, *reason)
