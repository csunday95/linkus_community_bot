
from typing import Optional
import aiohttp
from datetime import datetime


class BotBackendClient:
    """The client for the backend API"""
    def __init__(self,  client_session: aiohttp.ClientSession, api_url: str = 'http://localhost:8000/api/',):
        """
        Creates a BotBackendClient instance.

        :param client_session: The aiohttp ClientSession instance to use
        :param api_url: the base URL to use for API requests
        """
        self._api_url = api_url
        self._session = client_session

    async def discipline_type_get_list(self):
        """
        Gets a list of all discipline types as dictionaries.

        :return: A list of all discipline type instances as dictionaries containing {"discipline_name": str} or None
        on failure.
        """
        try:
            async with self._session.get(self._api_url + 'discipline-type') as response:
                if response.status != 200:
                    return None, f'Got error code from server: {response.status}'
                return await response.json(), None
        except aiohttp.ClientConnectionError:
            return None, 'Unable to contact database'

    async def discipline_type_get_by_name(self, type_name: str):
        """
        Get the discipline type instance matching the given name (case-insensitive).

        :param type_name: The name to search for a matching discipline type with
        :return: A tuple of ({"discipline_name": str}, None) on success or (None, error message) on failure.
        """
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
                                      discipline_end_date: Optional[datetime]) -> Optional[str]:
        """
        Creates a new discipline event instance.

        :param user_snowflake: The user that is being disciplined
        :param user_username: The username at the time of discipline to list
        :param moderator_snowflake: the moderator user that is causing this discipline event to be created
        :param discipline_type_id: the ID of the discipline type this event instance represents
        :param discipline_reason: the reason for this discipline
        :param discipline_end_date: the datetime at which this discipline will become terminated, or None if
        the discipline should be indefinite
        :return: None on success, an error message on failure
        """
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
        req_url = self._api_url + 'discipline-event/get_discipline_events_for/'
        try:
            async with self._session.get(req_url, params=params) as response:
                if response.status != 200:
                    raise ValueError(f'Encountered an HTTP error retrieving {req_url}: {response.status}')
                return await response.json()
        except aiohttp.ClientConnectionError:
            return None, 'Unable to contact database'

    async def discipline_event_get_latest_discipline_of_type(self, user_snowflake: int, discipline_name: str):
        """
        Attempts to get the latest discipline event applied to the given user of a given discipline type.

        :param user_snowflake: the user to search under
        :param discipline_name: the name of the discipline type to search under
        :return: A tuple of (discipline event dict, None) on success, or (None, error message) on failure. If a
        matching discipline even was not found, the returned discipline event option will be an empty dictionary {}.
        """
        params = {'user_snowflake': user_snowflake, 'discipline_name': discipline_name}
        req_url = self._api_url + 'discipline-event/get_latest_discipline/'
        try:
            async with self._session.get(req_url, params=params) as response:
                if response.status == 404:
                    return {}, None
                elif response.status != 200:
                    return None, f'Encountered an HTTP error retrieving {req_url}: {response.status}'
                return await response.json(), None
        except aiohttp.ClientConnectionError:
            return None, 'Unable to contact database'

    async def discipline_event_set_pardoned(self, event_id: int, is_pardoned: bool):
        """
        Sets the given discipline event (by ID) to have the given pardon state.

        :param event_id: The ID of the event to modify.
        :param is_pardoned: The new state to set the is_pardoned value to for the given event.
        :return: None on sucess, error message on failure
        """
        req_url = self._api_url + f'discipline-event/{event_id}/'
        patch_data = {'is_pardoned': is_pardoned}
        try:
            async with self._session.patch(req_url, data=patch_data) as response:
                if response.status != 200:
                    return f'Got error code from server: {response.status}'
                return None
        except aiohttp.ClientConnectionError:
            return 'Unable to contact database'

    async def discipline_event_get_latest_by_username(self, username: str):
        """
        Gets the latest discipline event for the given user by username. This searches for an exact, but case
        insensitive username match for which the most recent entry will be returned.

        :param username: the username to search for a match of
        :return: A tuple of (discipline event dict, None) on success, (None, error message) on failure.
        """
        req_url = self._api_url + 'discipline-event/get_latest_discipline_by_username/'
        params = {'username': username}
        try:
            async with self._session.get(req_url, params=params) as response:
                if response.status == 404:
                    return None, f'User by name {username} has never been disciplined'
                elif response.status != 200:
                    return None, f'Encountered HTTP error {response.status} when checking for user {username}'
                return await response.json(), None
        except aiohttp.ClientConnectionError:
            return None, 'Unable to contact database'
