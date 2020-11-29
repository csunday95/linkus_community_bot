from typing import Union
from discord.ext.commands import Cog, Bot, Context
from discord.ext import commands
from discord import Guild, Member, Message
from bot_backend_client import BotBackendClient, DisciplineConfiguration, ReactionConfiguration


class ConfigureBotCog(Cog):
    def __init__(self, bot: Bot, backend_client: BotBackendClient):
        self._bot = bot
        self._backend_client = backend_client

    async def on_guild_join(self, guild: Guild):
        """
        """
        owner = guild.owner  # type: Member
        welcome_message = f'Hello, {owner.mention}. The bot {self._bot.user.mention} has joined the server {guild.name} '
        'of which you are the owner. Some basic configuration is required for use in your guild, as follows:'
        await owner.send(welcome_message)
        await owner.send('What channel would you like to use for moderation commands?')

    @Cog.listener()
    async def on_message(self, message: Message):
        if message.author == self._bot.user:
            # ignore own messages
            return
        if message.guild is not None:
            # only check DMs
            return

    @commands.group(name='config')
    async def configure(self, ctx: Context):
        if ctx.subcommand_passed is None:
            await ctx.channel.send('No configuration subcommand given.')

    @configure.command()
    async def set(self, ctx: Context, parameter_name: str, parameter_value: Union[bool, str, int]):
        pass
