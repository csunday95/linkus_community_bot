from discord.ext.commands import Cog, Context, Bot
from discord import Guild, Member
from bot_backend_client import BotBackendClient


class ConfigureBotCog(Cog):
    def __init__(self, bot: Bot, backend_client: BotBackendClient):
        self._bot = bot
        self._backend_client = backend_client

    async def on_guild_join(self, guild: Guild):
        owner = guild.owner  # type: Member
        welcome_message = f'Hello, {owner.mention}. The bot {self._bot.user.mention} has joined the server {guild.name} '
        'of which you are the owner. Some basic configuration is required for use in your guild, as follows:'
        await owner.send(welcome_message)
        # TODO: back and forth to do basic configuration