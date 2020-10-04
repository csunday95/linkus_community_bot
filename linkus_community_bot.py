
from typing import List
import argparse
import json
from discord.ext.commands import Bot
from discipline_cog import DisciplineCog
import aiohttp
import sys
from bot_backend_client import BotBackendClient


class AIOSetupBot(Bot):

    def __init__(self, backend_auth_token: str, command_prefix: str, *args, **kwargs):
        self._backend_auth_token = backend_auth_token
        super().__init__(command_prefix, *args, **kwargs)

    async def start(self, *args, **kwargs):
        auth_header_dict = {'Authorization': f'Token {self._backend_auth_token}'}
        async with aiohttp.ClientSession(headers=auth_header_dict) as client_session:  # type: aiohttp.ClientSession
            backend_client = BotBackendClient(client_session)
            discipline_cog = DisciplineCog(self, backend_client)
            self.add_cog(discipline_cog)
            await super().start(*args, **kwargs)


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
    bot = AIOSetupBot(
        backend_auth_token=config['backend_authorization_code'],
        command_prefix=config['bot_prefix'],
        fetch_offline_members=True)
    bot.run(config['discord_bot_token'])
    print('bot exiting')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
