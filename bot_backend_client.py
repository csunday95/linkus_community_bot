
from typing import Optional
import aiohttp
from datetime import datetime


class BotBackendClient:
    def __init__(self,  client_session: aiohttp.ClientSession, api_url: str = 'http://localhost:8000/api/',):
        self._api_url = api_url
        self._session = client_session

    async def discipline_type_get_list(self):
        async with self._session.get(self._api_url + 'discipline-type') as response:
            if response.status != 200:
                return None
            return response.json()

    async def discipline_type_get_by_name(self, type_name: str):
        params = {'name': type_name}
        async with self._session.get(self._api_url + 'discipline-type/get_by_name', params=params) as response:
            if response.status != 200:
                return None
            return response.json()

    async def discipline_event_create(self,
                                      user_snowflake: int,
                                      user_username: str,
                                      moderator_snowflake: int,
                                      discipline_type_id: int,
                                      discipline_reason: str,
                                      discipline_end_date: Optional[datetime]):
        post_data = {
            "discord_user_snowflake": user_snowflake,
            "username_when_disciplined": user_username,
            "moderator_user_snowflake": moderator_snowflake,
            "reason_for_discipline": discipline_reason,
            "discipline_end_date_time": discipline_end_date,
            "discipline_type": discipline_type_id
        }
        async with self._session.post(self._api_url + 'discipline-event/', json=post_data) as response:
            if response.status != 200:
                print(response.status)
                return False
            print(response.json())
            return True
