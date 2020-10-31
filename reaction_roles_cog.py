from discord.ext import commands
from discord.ext.commands import Cog, Context, Bot
from discord import RawReactionActionEvent, Guild, Member, PartialEmoji, TextChannel, Role, Emoji, Message, Embed
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

    @commands.group()
    async def react(self, ctx: Context):
        if ctx.subcommand_passed is None:
            await ctx.channel.send('No moderation subcommand given.')

    @react.command()
    async def create(self, ctx: Context):
        """
        Creates a new reaction role embed entry and create message in management channel.

        :param ctx:
        """
        reaction_role_embed = Embed(
            title='Reaction Role Embed',
            description='Example Description'
        )
        message = await ctx.channel.send(content=None, embed=reaction_role_embed)  # type: Message
        sub_content = f'<@!{ctx.author.id}> Reaction Role message created:\n`{message.id}`\n'
        sub_content += f'{message.jump_url}'
        await message.edit(content=sub_content)

    @react.command()
    async def jump(self, ctx: Context, message: Message):
        """
        Reposts reaction role message preview and deletes the old one.

        :param ctx:
        :param message:
        """
        jump_link_embed = Embed(description=f'[jump]({message.jump_url})')
        await ctx.channel.send(f'<@!{ctx.author.id}> Link to given post:', embed=jump_link_embed)

    @react.command()
    async def last(self, ctx: Context):
        """
        Return the message ID and jump link for the last created reaction post in this guild.

        :param ctx:
        :return:
        """
        pass

    @react.command()
    async def add(self, ctx: Context, message: Message, emoji: Emoji, role: Role):
        """
        Adds a mapping of the given emoji to the given role for the given message.

        :param ctx:
        :param message:
        :param emoji:
        :param role:
        """
        pass

    @react.command()
    async def post(self, ctx: Context, message: Message, channel: TextChannel):
        """
        Posts a copy of the reaction role embed to the given channel.

        :param ctx:
        :param message:
        :param channel:
        :return:
        """
        pass
