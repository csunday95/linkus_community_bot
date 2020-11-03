
from typing import Tuple
from discord.ext import commands
from discord.ext.commands import Cog, Context, Bot
from discord import RawReactionActionEvent, Guild, Member, PartialEmoji, TextChannel, Role, Emoji, Message, Embed
from discord.abc import GuildChannel
from bot_backend_client import *


class ReactionRolesCog(Cog):

    def __init__(self, bot: Bot, backend_client: BotBackendClient):
        self._bot = bot
        self._backend_client = backend_client
        self._reaction_mapping_cache = {}  # type: Dict[int, Dict[int, Dict[int, int]]]

    async def _retrieve_reaction_emoji_role(self, guild: Guild, message_id: int, emoji: PartialEmoji) \
            -> Tuple[Optional[Role], Optional[str]]:
        """

        :param guild:
        :param message:
        :param emoji:
        :return:
        """
        # if this guild has been added while the bot has been running
        if guild.id not in self._reaction_mapping_cache:
            await self._populate_reaction_embed_guild_cache(guild)
        if message_id not in self._reaction_mapping_cache[guild.id]:
            return None, f'Message {message_id} is not a reaction role message'
        if emoji.id not in self._reaction_mapping_cache[guild.id][message_id]:
            # TODO: this might be a common case if unmapped reacts are allowed, make configurable?
            return None, f'Emoji {emoji} is not mapped to a role for message {message_id}'
        mapped_role_id = self._reaction_mapping_cache[guild.id][message_id][emoji.id]
        try:
            return guild.get_role(mapped_role_id), None
        except commands.RoleNotFound:
            return None, f'Emoji {emoji} seems to map to role ID {mapped_role_id}, which does not exist.'

    async def _populate_reaction_embed_guild_cache(self, guild: Guild):
        """

        :param guild: the guild to populate the cache for
        """
        reaction_embed_list, err = await self._backend_client.reaction_role_embed_list(guild.id)
        if reaction_embed_list is None:
            print(err)  # TODO: real error handling later
            return
        if guild.id not in self._reaction_mapping_cache:
            self._reaction_mapping_cache[guild.id] = {}
        for reaction_entry in reaction_embed_list:
            try:
                message_id = reaction_entry['message_snowflake']
                emoji_role_map_dict = {e['emoji_snowflake']: e['role_snowflake'] for e in reaction_entry['mappings']}
            except KeyError as e:
                return 'Encountered an error in backend formatting for message '\
                       f'entry {reaction_entry}, guild {guild}: {e}'
            self._reaction_mapping_cache[guild.id][message_id] = emoji_role_map_dict

    async def _populate_reaction_embed_cache(self):
        """

        """
        for guild in self._bot.guilds:
            if guild in self._reaction_mapping_cache:
                continue
            await self._populate_reaction_embed_guild_cache(guild)

    async def _handle_reaction_add(self, message_id: int, guild: Guild, member: Member, emoji: PartialEmoji):
        """
        Handles the actions that should be taken when a user adds a reaction to a reaction role message.

        :param message_id:
        :param guild:
        :param member:
        :param emoji:
        :return:
        """
        mapped_role, err = await self._retrieve_reaction_emoji_role(guild, message_id, emoji)
        if mapped_role is None:
            return f'Could not resolve role for given emoji {emoji}: {err}'
        await member.add_roles(mapped_role, reason=f'Reacted with {emoji} on message {message_id}')
        return None

    async def _handle_reaction_remove(self, message_id: int, guild: Guild, member: Member, emoji: PartialEmoji):
        mapped_role, err = await self._retrieve_reaction_emoji_role(guild, message_id, emoji)
        if mapped_role is None:
            return f'Could not resolve role for given emoji {emoji}: {err}'
        await member.remove_roles(mapped_role, reason=f'Unreacted with {emoji} on message {message_id}')
        return None

    def _convert_reaction_event(self, payload: RawReactionActionEvent):
        if payload.guild_id is None:
            return  # TODO: non-guild case, e.g. DM, how to handle later?
        guild = self._bot.get_guild(payload.guild_id)  # type: Guild
        if guild is None:
            # TODO: handle error case
            print('got none guild')
            return
        member = payload.member  # type: Member
        if member is None:
            if payload.event_type == 'REACTION_REMOVE' and payload.guild_id is not None:
                # in the remove case, we have to pull user/member by ID
                try:
                    member = guild.get_member(payload.user_id)
                except commands.MemberNotFound:
                    # TODO: error handling
                    print(f'Unable to find member {payload.user_id}')
                    return
            else:
                # TODO: error handling
                print('got non-guild message 2')
                return
        if member == self._bot.user:
            # ignore reactions added by bot
            return
        return guild, member

    @Cog.listener()
    async def on_ready(self):
        await self._populate_reaction_embed_cache()

    @Cog.listener()
    async def on_raw_reaction_add(self, payload: RawReactionActionEvent):
        if payload.event_type != 'REACTION_ADD':
            # TODO: error handling
            print('got non-add event')
            return
        guild, member = self._convert_reaction_event(payload)
        err = await self._handle_reaction_add(payload.message_id, guild, member, payload.emoji)
        if err is not None:
            # TODO: error feedback?
            print(err)

    @Cog.listener()
    async def on_raw_reaction_remove(self, payload: RawReactionActionEvent):
        if payload.event_type != 'REACTION_REMOVE':
            # TODO: error handling
            print('got non-remove event')
            return
        guild, member = self._convert_reaction_event(payload)
        err = await self._handle_reaction_remove(payload.message_id, guild, member, payload.emoji)
        if err is not None:
            # TODO: error feedback?
            print(err)

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
        # creating dictionary mapping emoji to roles from trailing arguments
        initial_map_dict = {}  # type: Dict[Emoji, Role]
        initial_id_map_dict = {}  # type: Dict[int, int]
        if len(initial_mappings) > 0:
            # trailing arguments must have an even length
            if len(initial_mappings) % 2 != 0:
                await ctx.channel.send(f'{ctx.author.mention} Uneven number of initial mapping parameters given!')
                return
            emoji_converter = commands.EmojiConverter()
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
                except commands.EmojiNotFound:
                    await ctx.channel.send(f'{ctx.author.mention} Unable to convert {emoji_arg} to an emoji.')
                    return
                except commands.RoleNotFound:
                    await ctx.channel.send(f'{ctx.author.mention} Unable to convert {role_arg} to a role.')
                    return
                initial_map_dict[emoji] = role
                initial_id_map_dict = {emoji.id: role.id for emoji, role in initial_map_dict.items()}
        message = await ctx.channel.send(content='Creating new reaction role message....')  # type: Message
        created, err = await self._backend_client.reaction_role_embed_create(
            message_snowflake=message.id,
            guild_snowflake=ctx.guild.id,
            creating_member_snowflake=ctx.author.id,
            emoji_role_mapping=initial_id_map_dict
        )
        if created is None:
            msg = f'{ctx.author.mention} Encountered an error creating mapping embed on backend: {err}'
            await message.edit(content=msg)
            return
        guild_id = ctx.guild.id
        if guild_id not in self._reaction_mapping_cache:
            self._reaction_mapping_cache[guild_id] = {}
        self._reaction_mapping_cache[guild_id][message.id] = initial_id_map_dict.copy()
        sub_content = f'{ctx.author.mention} Reaction Role message created:\nID=`{message.id}`\n'
        sub_content += f'{message.jump_url}'
        generated_description = ['{} -> {}'.format(e, r.mention) for e, r in initial_map_dict.items()]
        reaction_role_embed = Embed(
            title='Reaction Role Embed',
            description='\n'.join(generated_description)
        )
        await message.edit(content=sub_content, embed=reaction_role_embed)
        for emoji in initial_map_dict.keys():
            await message.add_reaction(emoji)

    @react.command()
    async def edit(self, ctx: Context, message: Message):
        await ctx.channel.send(f'{ctx.author.mention} Not Yet Implemented')

    @react.command()
    async def delete(self, ctx: Context, message: Message):
        """
        Deletes the given reaction role message/embed.

        :param ctx:
        :param message:
        :return:
        """
        await ctx.channel.send(f'{ctx.author.mention} Not Yet Implemented')

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
        await ctx.channel.send(f'{ctx.author.mention} Not Yet Implemented')

    @react.command()
    async def add(self, ctx: Context, message: Message, emoji: Emoji, role: Role):
        """
        Adds a mapping of the given emoji to the given role for the given message.

        :param ctx:
        :param message:
        :param emoji:
        :param role:
        """
        try:
            mapping_dict = self._reaction_mapping_cache[ctx.guild.id][message.id]
        except KeyError:
            await ctx.channel.send(f'{ctx.author.mention} Reaction role embed message {message.id} does not exist')
            return
        err = await self._backend_client.reaction_role_embed_add_mappings(
            guild_snowflake=ctx.guild.id,
            message_snowflake=message.id,
            emoji_role_mappings={emoji.id: role.id}
        )
        if err is not None:
            await ctx.channel.send(f'{ctx.author.mention} Unable to add mapping to backend: {err}')
            return
        mapping_dict[emoji.id] = role.id
        await message.add_reaction(emoji)
        await ctx.channel.send(f'{ctx.author.mention} Reaction role mapping of {emoji} to {role} added')

    @react.command()
    async def remove(self, ctx: Context, message: Message, emoji: Emoji):
        """
        Remove the given emoji from having a mapping

        :param ctx:
        :param message:
        :param emoji:
        :return:
        """
        await ctx.channel.send(f'{ctx.author.mention} Not Yet Implemented')

    @react.command()
    async def post(self, ctx: Context, message: Message, channel: TextChannel):
        """
        Posts a copy of the reaction role embed to the given channel.

        :param ctx:
        :param message:
        :param channel:
        :return:
        """
        await ctx.channel.send(f'{ctx.author.mention} Not Yet Implemented')
