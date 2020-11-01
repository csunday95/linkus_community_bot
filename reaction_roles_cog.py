
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
        if member == self._bot.user:
            # ignore reactions added by bot
            return
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
    async def create(self, ctx: Context, *initial_mappings: str):
        """
        Creates a new reaction role embed entry and create message in management channel.

        :param ctx:
        """
        reaction_role_embed = Embed(
            title='Reaction Role Embed',
            description='Example Description'
        )
        # creating dictionary mapping emoji to roles from trailing arguments
        initial_map_dict = {}
        if len(initial_mappings) > 0:
            # trailing arguments must have an even length
            if len(initial_mappings) % 2 != 0:
                await ctx.channel.send(f'{ctx.author.mention} Uneven number of initial mapping parameters given!')
                return
            emoji_converter = commands.PartialEmojiConverter()
            role_converter = commands.RoleConverter()
            for idx in range(0, len(initial_mappings), 2):
                try:
                    emoji_arg, role_arg = initial_mappings[idx:idx+2]
                except IndexError:
                    await ctx.channel.send(f'{ctx.author.mention} Uneven number of initial mapping parameters given!')
                    return
                try:
                    emoji = await emoji_converter.convert(ctx, emoji_arg)
                    role = await role_converter.convert(ctx, role_arg)
                except commands.PartialEmojiConversionFailure:
                    await ctx.channel.send(f'{ctx.author.mention} Unable to convert {emoji_arg} to an emoji.')
                    return
                except commands.RoleNotFound:
                    await ctx.channel.send(f'{ctx.author.mention} Unable to convert {role_arg} to a role.')
                    return
                initial_map_dict[emoji.id] = role.id
        message = await ctx.channel.send(content='Creating new reaction role message....')  # type: Message
        created, err = await self._backend_client.reaction_role_embed_create(
            message_snowflake=message.id,
            guild_snowflake=ctx.guild.id,
            creating_member_snowflake=ctx.author.id,
            emoji_role_mapping=initial_map_dict
        )
        if created is None:
            msg = f'{ctx.author.mention} Encountered an error creating mapping embed on backend: {err}'
            await message.edit(content=msg)
            return
        sub_content = f'{ctx.author.mention} Reaction Role message created:\n`{message.id}`\n'
        sub_content += f'{message.jump_url}'
        await message.edit(content=sub_content, embed=reaction_role_embed)

    @react.command()
    async def delete(self, ctx: Context, message: Message):
        """
        Deletes the given reaction role message/embed.

        :param ctx:
        :param message:
        :return:
        """
        await message.delete()

    @react.command()
    async def jump(self, ctx: Context, message: Message):
        """
        Reposts reaction role message preview and deletes the old one.

        :param ctx:
        :param message:
        """
        jump_link_embed = Embed(description=f'[jump]({message.jump_url})')
        await ctx.channel.send(f'{ctx.author.mention} Link to given post:', embed=jump_link_embed)

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
        await message.add_reaction(emoji)

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
