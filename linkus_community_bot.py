
from typing import List
import argparse
import json
from discord.ext.commands import Bot, Context, CommandError
from discord.ext import commands
from discord import Intents
from discipline_cog import DisciplineCog
from reaction_roles_cog import ReactionRolesCog
from configure_bot_cog import ConfigureBotCog
import aiohttp
import sys
from bot_backend_client import BotBackendClient

# https://discord.com/api/oauth2/authorize?client_id=754719676541698150&scope=bot&permissions=268921926


class AIOSetupBot(Bot):

    def __init__(self, backend_auth_token: str, command_prefix: str, *args, **kwargs):
        self._backend_auth_token = backend_auth_token
        super().__init__(command_prefix, *args, **kwargs)

    async def start(self, *args, **kwargs):
        auth_header_dict = {'Authorization': f'Token {self._backend_auth_token}'}
        async with aiohttp.ClientSession(headers=auth_header_dict) as client_session:  # type: aiohttp.ClientSession
            backend_client = BotBackendClient(client_session)
            discipline_cog = DisciplineCog(self, backend_client)
            reaction_roles_cog = ReactionRolesCog(self, backend_client)
            configure_cog = ConfigureBotCog(self, backend_client)
            self.add_cog(discipline_cog)
            self.add_cog(reaction_roles_cog)
            self.add_cog(configure_cog)
            await super().start(*args, **kwargs)

    async def on_command_error(self, ctx: Context, error: CommandError):
        """
        TODO: replace this with a dictionary for performance?

        :param ctx:
        :param error:
        :return:
        """
        sender_prefix = ctx.author.mention
        channel = ctx.channel
        if isinstance(error, commands.ConversionError):
            await channel.send(f'{sender_prefix} Unable to convert argument: `{error.original}`')
        elif isinstance(error, commands.MissingRequiredArgument):
            await channel.send(f'{sender_prefix} Argument `{error.param.name}` was not provided')
        elif isinstance(error, commands.ArgumentParsingError):
            await channel.send(f'{sender_prefix} Unable to parse arguments due to bad quoting.')
        elif isinstance(error, commands.BadUnionArgument):
            await channel.send(f'{sender_prefix} Argument `{error.param.name}` is improperly formatted')
        elif isinstance(error, commands.CommandNotFound):
            await channel.send(f'{sender_prefix} Command `{ctx.invoked_with}` is unknown.')
        elif isinstance(error, commands.DisabledCommand):
            await channel.send(f'{sender_prefix} Command `{ctx.command}` is disabled')
        elif isinstance(error, commands.CommandInvokeError):
            print(error)
            error_msg = f'{sender_prefix} Encountered an internal error while executing, please report to maintainer: '
            error_msg += f'```\n{error.original}\n```'
            await channel.send(error_msg)
        elif isinstance(error, commands.TooManyArguments):
            await channel.send(f'{sender_prefix} Too many arguments provided for command `{ctx.command}`')
        elif isinstance(error, commands.CommandOnCooldown):
            return
        elif isinstance(error, (commands.MemberNotFound, commands.UserNotFound)):
            await channel.send(f'{sender_prefix} Member/User `{error.argument}` could not be found as provided')
        elif isinstance(error, commands.ChannelNotFound):
            await channel.send(f'{sender_prefix} Channel `{error.argument}` could not be found as provided.')
        elif isinstance(error, commands.ChannelNotReadable):
            msg = f'{sender_prefix} This bot does not have permission to read channel `{error.argument}`'
            await channel.send(msg)
        elif isinstance(error, commands.RoleNotFound):
            await channel.send(f'{sender_prefix} The role `{error.argument}` could not be found as provided.')
        elif isinstance(error, commands.EmojiNotFound):
            await channel.send(f'{sender_prefix} The Emoji `{error.argument}` could not be found as provided')
        elif isinstance(error, commands.MessageNotFound):
            await channel.send(f'{sender_prefix} Message `{error.argument}` could not be found as provided.')
        else:
            await channel.send(f'{sender_prefix} Encountered an unknown error: `{error}`')


def main(args: List[str]):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'configuration_file',
        help='the path to the desired bot configuration file'
    )
    parse_result = vars(parser.parse_args(args))
    with open(parse_result['configuration_file'], 'r') as config_file:
        try:
            config = json.load(config_file)
        except (ValueError, TypeError) as e:
            print(f'Encountered error loading configuration file: {e}')
            return 1
    bot_intents = Intents.default()
    bot_intents.members = True
    bot = AIOSetupBot(
        backend_auth_token=config['backend_authorization_code'],
        command_prefix=config['bot_prefix'],
        fetch_offline_members=True,
        intents=bot_intents
    )
    bot.run(config['discord_bot_token'])
    print('bot exiting')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
