from discord.ext import commands
from discord.ext.commands import Cog, Context, Bot
from discord import RawReactionActionEvent, Guild, Member, PartialEmoji, TextChannel
from discord.abc import GuildChannel
from bot_backend_client import *


class ReactionRolesCog(Cog):

    def __init__(self, bot: Bot, backend_client: BotBackendClient):
        self._bot = bot
        self._backend_client = backend_client

    async def _resolve_tracked_embed(self):
        pass

    async def _handle_reaction_add(self, guild: Guild, channel: GuildChannel, member: Member, emoji: PartialEmoji):
        emoji_snowflake = emoji.id

    @Cog.listener()
    async def on_raw_reaction_add(self, payload: RawReactionActionEvent):
        if payload.event_type != 'REACTION_ADD':
            # TODO: error handling
            print('got non-add event')
            return
        if payload.guild_id is None:
            return  # non-guild case, shouldn't be possible
        member = payload.member  # type: Member
        guild = self._bot.get_guild(payload.guild_id)  # type: Guild
        if guild is None:
            # TODO: handle error case
            print('got none guild')
            return
        channel = self._bot.get_channel(payload.channel_id)  # type: GuildChannel
        if channel is None:
            # TODO: handle error
            print('got none channel')
            return
        if not isinstance(channel, TextChannel):
            # TODO: handle error
            print('got non-text channel')
            return
        message = await channel.fetch_message(payload.message_id)
        await self._handle_reaction_add(guild, channel, member, payload.emoji)

    @Cog.listener()
    async def on_raw_reaction_remove(self, payload: RawReactionActionEvent):
        print(payload)
