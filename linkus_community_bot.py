
from typing import List
import argparse
from discord.ext.commands import Bot
from discipline_cog import DisciplineCog

PREFIX = '!lonkus'
BOT_TOKEN = '754719676541698150'


def main(args: List[str]):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'arg',
        nargs='?',
        default=None
    )
    parse_result = vars(parser.parse_args(args))
    bot = Bot(PREFIX, fetch_offline_members=True)
    discipline_cog = DisciplineCog()
    bot.add_cog()
    bot.run(BOT_TOKEN)
    return 0
