
from typing import List
import argparse
from discord.ext.commands import Bot
from discipline_cog import DisciplineCog
import aiohttp
import sys
from bot_backend_client import BotBackendClient

PREFIX = '!lonkus '
BOT_TOKEN = 'NzU0NzE5Njc2NTQxNjk4MTUw.X141eA.P1RbUqXoc_eWnQgwZGfjVJ7hajY'


class AIOSetupBot(Bot):
    async def start(self, *args, **kwargs):
        async with aiohttp.ClientSession() as client_session:  # type: aiohttp.ClientSession
            backend_client = BotBackendClient(client_session)
            discipline_cog = DisciplineCog(self, backend_client)
            self.add_cog(discipline_cog)
            await super().start(*args, **kwargs)


def main(args: List[str]):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'arg',
        nargs='?',
        default=None
    )
    parse_result = vars(parser.parse_args(args))
    bot = AIOSetupBot(PREFIX, fetch_offline_members=True)
    bot.run(BOT_TOKEN)
    print('bot exiting')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
