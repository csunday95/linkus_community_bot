
from typing import Tuple
from discord.ext import commands
from discord.ext.commands import Cog, Context, Bot
from discord import RawReactionActionEvent, Guild, Member, PartialEmoji, TextChannel, Role, Emoji, Message, Embed
from bot_backend_client import *
from asyncio import Lock


class ReactionRolesCog(Cog):

    def __init__(self, bot: Bot, backend_client: BotBackendClient):
        self._bot = bot
        self._backend_client = backend_client
        self._mapping_cache_lock = Lock()
        self._reaction_mapping_cache = {}  # type: Dict[int, Dict[int, Dict[int, int]]]

    async def _retrieve_reaction_emoji_role(self, guild: Guild, message_id: int, emoji: PartialEmoji) \
            -> Tuple[Optional[Role], Optional[str]]:
        """

        :param guild:
        :param message_id:
        :param emoji:
        :return:
        """
        # if this guild has been added while the bot has been running
        if guild.id not in self._reaction_mapping_cache:
            await self._populate_reaction_embed_guild_cache(guild)
        async with self._mapping_cache_lock:
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

    async def _populate_reaction_embed_guild_cache(self, guild: Guild) -> Optional[str]:
        """

        :param guild: the guild to populate the cache for
        :return:
        """
        reaction_embed_list, err = await self._backend_client.reaction_role_embed_list(guild.id)
        if reaction_embed_list is None:
            return f'Unable to retrieve reaction role embed list: {err}'
        async with self._mapping_cache_lock:
            if guild.id not in self._reaction_mapping_cache:
                self._reaction_mapping_cache[guild.id] = {}
            for reaction_entry in reaction_embed_list:
                try:
                    message_id = reaction_entry['message_snowflake']
                    emoji_role_map_dict = \
                        {e['emoji_snowflake']: e['role_snowflake'] for e in reaction_entry['mappings']}
                except KeyError as e:
                    return 'Encountered an error in backend formatting for message '\
                           f'entry {reaction_entry}, guild {guild}: {e}'
                self._reaction_mapping_cache[guild.id][message_id] = emoji_role_map_dict
        return None

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

    def _convert_reaction_event(self, payload: RawReactionActionEvent) -> Tuple[Optional[Guild], Optional[Member]]:
        """
        Convert raw reaction event into the relevant guild and member.

        :param payload:
        :return:
        """
        if payload.guild_id is None:
            print('non guild react')
            return None, None  # TODO: non-guild case, e.g. DM, how to handle later?
        guild = self._bot.get_guild(payload.guild_id)  # type: Guild
        if guild is None:
            # TODO: handle error case
            print('got none guild')
            return None, None
        member = payload.member  # type: Member
        if member is None:
            if payload.event_type == 'REACTION_REMOVE' and payload.guild_id is not None:
                # in the remove case, we have to pull user/member by ID
                try:
                    member = guild.get_member(payload.user_id)
                except commands.MemberNotFound:
                    # TODO: error handling
                    print(f'Unable to find member {payload.user_id}')
                    return None, None
            else:
                # TODO: error handling
                print('got non-guild message 2')
                return None, None
        return guild, member

    async def _create_on_backend(self, message: Message, guild: Guild, author: Member, id_mapping: Dict[int, int]):
        created, err = await self._backend_client.reaction_role_embed_create(
            message_snowflake=message.id,
            guild_snowflake=guild.id,
            creating_member_snowflake=author.id,
            emoji_role_mapping=id_mapping
        )
        if created is None:
            return err
        # update cache
        guild_id = guild.id
        async with self._mapping_cache_lock:
            if guild_id not in self._reaction_mapping_cache:
                self._reaction_mapping_cache[guild_id] = {}
            self._reaction_mapping_cache[guild_id][message.id] = id_mapping.copy()
        return None

    async def _convert_emoji_role_id_map(self, guild: Guild, mapping: Dict[int, int]) -> Optional[Dict[Emoji, Role]]:
        """

        :param mapping:
        :return:
        """
        try:
            return {self._bot.get_emoji(emoji): guild.get_role(role) for emoji, role in mapping.items()}
        except commands.EmojiNotFound:
            return None
        except commands.RoleNotFound:
            return None

    def _is_message_tracked(self, guild: Guild, message: Message):
        try:
            return message.id in self._reaction_mapping_cache[guild.id]
        except KeyError:
            return False

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
        if member is None or member == self._bot.user:
            return
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
        err = await self._create_on_backend(message, ctx.guild, ctx.author, initial_id_map_dict)
        if err is not None:
            msg = f'{ctx.author.mention} Encountered an error creating mapping embed on backend: {err}'
            await message.edit(content=msg)
            return
        sub_content = f'{ctx.author.mention} Reaction Role message created:\nID=`{ctx.channel.id}-{message.id}`\n'
        sub_content += f'{message.jump_url}'
        generated_description = ['{} -> {}'.format(e, r.mention) for e, r in initial_map_dict.items()]
        reaction_role_embed = Embed(
            title='Reaction Role Embed',
            description='\n'.join(generated_description)
        )
        await message.edit(content=sub_content, embed=reaction_role_embed)
        for emoji in initial_map_dict.keys():
            await message.add_reaction(emoji)

    @react.group(name='edit')
    async def edit_group(self, ctx: Context):
        """

        :param ctx:
        """
        if ctx.subcommand_passed is None:
            await ctx.channel.send('No reaction role edit subcommand given.')

    @edit_group.command(name='title')
    async def edit_title(self, ctx: Context, message: Message, *, new_title: str):
        """

        :param ctx:
        :param message:
        :param new_title:
        :return:
        """
        if not self._is_message_tracked(ctx.guild, message):
            await ctx.channel.send(f'{ctx.author.mention} Message {message.id} is not a reaction role embed.')
            return
        embed = message.embeds[0]
        embed.title = new_title
        await message.edit(embed=embed)
        await ctx.channel.send(f'{ctx.author.mention} Title has been edited.')

    @edit_group.command(name='message')
    async def edit_message_content(self, ctx: Context, message: Message, *, new_content: str):
        """

        :param ctx:
        :param message:
        :param new_content:
        :return:
        """
        if not self._is_message_tracked(ctx.guild, message):
            await ctx.channel.send(f'{ctx.author.mention} Message {message.id} is not a reaction role embed.')
            return
        await message.edit(content=new_content)
        await ctx.channel.send(f'{ctx.author.mention} Message content has been edited.')

    @edit_group.command(name='description')
    async def edit_embed_description(self, ctx: Context, message: Message, *, new_description: str):
        """

        :param ctx:
        :param message:
        :param new_description:
        :return:
        """
        if not self._is_message_tracked(ctx.guild, message):
            await ctx.channel.send(f'{ctx.author.mention} Message {message.id} is not a reaction role embed.')
            return
        current_embed = message.embeds[0]
        current_embed.description = new_description
        await message.edit(embed=current_embed)
        await ctx.channel.send(f'{ctx.author.mention} Reaction embed description has been edited.')

    @edit_group.command(name='append_description')
    async def append_embed_description(self, ctx: Context, message: Message, *, to_append: str):
        if not self._is_message_tracked(ctx.guild, message):
            await ctx.channel.send(f'{ctx.author.mention} Message {message.id} is not a reaction role embed.')
            return
        current_embed = message.embeds[0]
        current_embed.description += f'\n{to_append}'
        await message.edit(embed=current_embed)
        await ctx.channel.send(f'{ctx.author.mention} Reaction embed description has been appended to.')

    @react.command()
    async def delete(self, ctx: Context, message: Message):
        """
        Deletes the given reaction role message/embed.

        :param ctx:
        :param message:
        :return:
        """
        err = await self._backend_client.reaction_role_embed_delete(
            guild_snowflake=ctx.guild.id,
            message_snowflake=message.id
        )
        if err is not None:
            await ctx.channel.send(f'{ctx.author.mention} Unable to delete message: {err}')
            return
        target_message = ctx.message  # type: Message
        await target_message.delete()
        try:
            self._reaction_mapping_cache[ctx.guild.id].pop(message.id)
        except KeyError as e:
            # TODO: log this to logging channel?
            print(f'Encountered an error clearing cache on react embed delete: {e}')

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
    async def add(self, ctx: Context, message: Message, emoji: Emoji, role: Role, *description: str):
        """
        Adds a mapping of the given emoji to the given role for the given message.

        :param ctx:
        :param message:
        :param emoji:
        :param role:
        :param description:
        """
        if len(description) > 0:
            # supports {emoji} and {role} replacement
            description = ' '.join(description)
        else:
            # TODO: add configurable default description format
            description = '{emoji} -> {role}'
        description = description.format(emoji=emoji, role=role.mention)
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
        embed = message.embeds[0]
        embed.description += f'\n{description}'
        await ctx.channel.send(f'{ctx.author.mention} Reaction role mapping of {emoji} to {role} added')

    @react.command()
    async def remove(self, ctx: Context, message: Message, emoji: Emoji):
        """
        Remove the given emoji from having a mapping.

        :param ctx:
        :param message:
        :param emoji:
        :return:
        """
        try:
            mapping_dict = self._reaction_mapping_cache[ctx.guild.id][message.id]
        except KeyError:
            msg = f'{ctx.author.mention} Reaction role embed message {ctx.channel.id}-{message.id} does not exist'
            await ctx.channel.send(msg)
            return
        emoji_id = emoji.id
        if emoji_id not in mapping_dict:
            msg = f'{ctx.author.mention} Reaction role embed message {ctx.channel.id}-{message.id} ' \
                  f'does not have a mapping for emoji {emoji}'
            await ctx.channel.send(msg)
        err = await self._backend_client.reaction_role_embed_remove_mappings(
            guild_snowflake=ctx.guild.id,
            message_snowflake=message.id,
            emoji_ids=[emoji.id]
        )
        if err is not None:
            await ctx.channel.send(f'{ctx.author.mention} Unable to remove mapping from backend: {err}')
            return
        mapping_dict.pop(emoji.id)
        # TODO: add configuration for removing role from all people that had reacted?
        await message.clear_reaction(emoji)
        msg = f'{ctx.author.mention} Removed mapping for emoji {emoji} from message {ctx.channel.id}-{message.id}'
        await ctx.channel.send(msg)

    @react.command()
    async def post(self, ctx: Context, message: Message, to_channel: TextChannel):
        """
        Posts a copy of the reaction role embed to the given channel and register it as a new reaction role
        embed.

        :param ctx:
        :param message:
        :param to_channel:
        """
        embed_info, err = await self._backend_client.reaction_role_embed_get(message.id, ctx.guild.id)
        if embed_info is None:
            msg = f'{ctx.author.mention} Unable to retrieve reaction role info for message ' \
                  f'{ctx.channel.id}-{message.id}: {err}'
            await ctx.channel.send(msg)
            return
        new_message = await to_channel.send(content=message.content, embed=message.embeds[0])
        emoji_role_mappings = embed_info['mappings']
        emoji_list = [self._bot.get_emoji(emoji_id) for emoji_id in emoji_role_mappings.keys()]
        err = await self._create_on_backend(
            new_message, ctx.guild, ctx.author, emoji_role_mappings
        )
        if err is not None:
            await ctx.channel.send(f'{ctx.author.mention} Unable to create new reaction role embed: {err}')
            await new_message.delete()
            return
        for emoji in emoji_list:
            await new_message.add_reaction(emoji)
        msg = f'{ctx.author.mention} New message created with ID=`{ctx.channel.id}-{new_message.id}`'
        await ctx.channel.send(msg)
