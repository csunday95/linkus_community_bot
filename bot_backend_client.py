
from typing import Optional
import aiohttp
from datetime import datetime


class BotBackendClient:
    def __init__(self,  client_session: aiohttp.ClientSession, api_url: str = 'http://localhost:8000/api/',):
        self._api_url = api_url
        self._session = client_session

    async def discipline_type_get_list(self):
        try:
            async with self._session.get(self._api_url + 'discipline-type') as response:
                if response.status != 200:
                    return None, f'Got error code from server: {response.status}'
                return await response.json(), None
        except aiohttp.ClientConnectionError:
            return None, 'Unable to contact database'

    async def discipline_type_get_by_name(self, type_name: str):
        params = {'name': type_name}
        try:
            async with self._session.get(self._api_url + 'discipline-type/get_by_name/', params=params) as response:
                if response.status != 200:
                    return None, f'Got error code from server: {response.status}'
                return await response.json(), None
        except aiohttp.ClientConnectionError:
            return None, 'Unable to contact database'

    async def discipline_event_create(self,
                                      user_snowflake: int,
                                      user_username: str,
                                      moderator_snowflake: int,
                                      discipline_type_id: int,
                                      discipline_reason: str,
                                      discipline_end_date: Optional[datetime]):
        if discipline_end_date is not None:
            discipline_end_date = discipline_end_date.isoformat()
        post_data = {
            "discord_user_snowflake": user_snowflake,
            "username_when_disciplined": user_username,
            "moderator_user_snowflake": moderator_snowflake,
            "reason_for_discipline": discipline_reason,
            "discipline_end_date_time": discipline_end_date,
            "discipline_type": discipline_type_id
        }
        req_url = self._api_url + 'discipline-event/'
        try:
            async with self._session.post(req_url, json=post_data) as response:
                if response.status != 201:
                    return f'Encountered an HTTP error retrieving {req_url}: {response.status}'
                return None
        except aiohttp.ClientConnectionError:
            return 'Unable to contact database'

    async def discipline_event_get_all_for_user(self, user_snowflake: int):
        params = {'user_snowflake': user_snowflake}
        req_url = self._api_url + 'discipline-event/get-discipline-events-for/'
        try:
            async with self._session.get(req_url, params=params) as response:
                if response.status != 200:
                    raise ValueError(f'Encountered an HTTP error retrieving {req_url}: {response.status}')
                return await response.json()
        except aiohttp.ClientConnectionError:
            return None, 'Unable to contact database'

    async def discipline_event_get_latest_ban(self, user_snowflake: int):
        params = {'user_snowflake': user_snowflake, 'discipline_name': 'ban'}
        req_url = self._api_url + 'discipline-event/is-user-banned/'
        try:
            async with self._session.get(req_url, params=params) as response:
                if response.status == 404:
                    return {}, None
                elif response.status != 200:
                    return None, f'Encountered an HTTP error retrieving {req_url}: {response.status}'
                return await response.json(), None
        except aiohttp.ClientConnectionError:
            return None, 'Unable to contact database'
