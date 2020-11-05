
from typing import Optional, Dict, List
import aiohttp
import uuid
from datetime import datetime


class BotBackendClient:
    """The client for the backend API"""
    def __init__(self,
                 client_session: aiohttp.ClientSession,
                 api_url: str = 'http://localhost:8000/api/'):
        """
        Creates a BotBackendClient instance.

        :param client_session: The aiohttp ClientSession instance to use
        :param api_url: the base URL to use for API requests
        """
        # TODO: break this out to also store origin guild snowflake
        # TODO: add overall pagination support for multiple response requests
        self._api_url = api_url
        self._session = client_session

    async def discipline_type_get_list(self):
        """
        Gets a list of all discipline types as dictionaries.

        :return: A list of all discipline type instances as dictionaries containing {"discipline_name": str} or None
        on failure.
        """
        try:
            async with self._session.get(self._api_url + 'discipline/discipline-type') as response:
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
        endpoint_url = self._api_url + 'discipline/discipline-type/get_by_name'
        try:
            async with self._session.get(endpoint_url, params=params) as response:
                if response.status != 200:
                    return None, f'Got error code from server: {response.status}'
                return await response.json(), None
        except aiohttp.ClientConnectionError:
            return None, 'Unable to contact database'

    async def discipline_event_create(self,
                                      guild_snowflake: int,
                                      guild_name: str,
                                      user_snowflake: int,
                                      user_username: str,
                                      moderator_snowflake: int,
                                      moderator_username: str,
                                      discipline_type_id: int,
                                      discipline_content: Optional[str],
                                      discipline_reason: str,
                                      discipline_end_date: Optional[datetime],
                                      immediately_terminated: bool = False):
        """
        Creates a new discipline event instance.

        :param guild_snowflake: the id of the guild to create this entry for
        :param guild_name: the name of the guild at the time of event creation
        :param user_snowflake: The user that is being disciplined
        :param user_username: The username at the time of discipline to list
        :param moderator_snowflake: the moderator user that is causing this discipline event to be created
        :param moderator_username: the username of the moderator at the time of event creation
        :param discipline_type_id: the ID of the discipline type this event instance represents
        :param discipline_content: the content/data relevant to this discipline event if any
        :param discipline_reason: the reason for this discipline
        :param discipline_end_date: the datetime at which this discipline will become terminated, or None if
        the discipline should be indefinite
        :param immediately_terminated: if True, this discipline event entry will be created in a terminated state.
        :return: A tuple of (created event dict, None) on success or (None, error message) on failure
        """
        if discipline_end_date is not None:
            discipline_end_date = discipline_end_date.isoformat()
        post_data = {
            "discord_guild_snowflake": guild_snowflake,
            "discord_guild_name": guild_name,
            "discord_user_snowflake": user_snowflake,
            "username_when_disciplined": user_username,
            "moderator_user_snowflake": moderator_snowflake,
            "moderator_username": moderator_username,
            "reason_for_discipline": discipline_reason,
            "discipline_end_date_time": discipline_end_date,
            "discipline_type": discipline_type_id,
            "discipline_content": '' if discipline_content is None else discipline_content
        }
        if immediately_terminated:
            post_data['is_terminated'] = True
        req_url = self._api_url + 'discipline/discipline-event/'
        try:
            async with self._session.post(req_url, json=post_data) as response:
                if response.status != 201:
                    print(await response.content.read())
                    return None, f'Encountered an HTTP error creating at {req_url}: {response.status}'
                return await response.json(), None
        except aiohttp.ClientConnectionError:
            return None, 'Unable to contact database'

    async def discipline_event_get(self, discipline_event_id: uuid.UUID):
        """
        Gets the discipline event dict for a particular database ID.

        :param discipline_event_id: the database id of the discipline event to retrieve
        :return: A tuple of (Discipline Event Dict, None) on success, (None, error message) on failure
        """
        req_url = self._api_url + f'discipline/discipline-event/{discipline_event_id}/'
        try:
            async with self._session.get(req_url) as response:
                if response.status != 200:
                    raise ValueError(f'Encountered an HTTP error retrieving {req_url}: {response.status}')
                return await response.json(), None
        except aiohttp.ClientConnectionError:
            return None, 'Unable to contact database'

    async def discipline_event_get_all_for_user(self, guild_snowflake: int, user_snowflake: int):
        """
        Gets all user discipline events for a given discord user.

        :param guild_snowflake: the discord snowflake to filter guild by
        :param user_snowflake: The discord snowflake to user filter by
        :return: A tuple of (list of discipline event dicts, None) on success, or (None, error message) on failure
        """
        params = {'guild_snowflake': guild_snowflake, 'user_snowflake': user_snowflake}
        req_url = self._api_url + 'discipline/discipline-event/get_discipline_events_for'
        results = []
        while req_url is not None:
            try:
                async with self._session.get(req_url, params=params) as response:
                    if response.status != 200:
                        raise ValueError(f'Encountered an HTTP error retrieving {req_url}: {response.status}')
                    result = await response.json()
                    if 'next' in result:
                        results += result['results']
                        req_url = result['next']
                    else:
                        req_url = None
            except aiohttp.ClientConnectionError:
                return None, 'Unable to contact database'
        return results, None

    async def discipline_event_get_latest_discipline_of_type(self,
                                                             guild_snowflake: int,
                                                             user_snowflake: int,
                                                             discipline_name: str):
        """
        Attempts to get the latest discipline event applied to the given user of a given discipline type.

        :param guild_snowflake: the guild to search under
        :param user_snowflake: the user to search under
        :param discipline_name: the name of the discipline type to search under
        :return: A tuple of (discipline event dict, None) on success, or (None, error message) on failure. If a
        matching discipline even was not found, the returned discipline event option will be an empty dictionary {}.
        """
        params = {
            'guild_snowflake': guild_snowflake, 'user_snowflake': user_snowflake, 'discipline_name': discipline_name
        }
        req_url = self._api_url + 'discipline/discipline-event/get_latest_discipline'
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
        req_url = self._api_url + f'discipline/discipline-event/{event_id}/'
        patch_data = {'is_pardoned': is_pardoned}
        try:
            async with self._session.patch(req_url, data=patch_data) as response:
                if response.status != 200:
                    return f'Got error code from server: {response.status}'
                return None
        except aiohttp.ClientConnectionError:
            return 'Unable to contact database'

    async def discipline_event_get_latest_by_username(self, guild_snowflake: int, username: str):
        """
        Gets the latest discipline event for the given user by username. This searches for an exact, but case
        insensitive username match for which the most recent entry will be returned.

        :param guild_snowflake:
        :param username: the username to search for a match of
        :return: A tuple of (discipline event dict, None) on success, (None, error message) on failure.
        """
        req_url = self._api_url + 'discipline/discipline-event/get_latest_discipline_by_username'
        params = {'guild_snowflake': guild_snowflake, 'username': username}
        try:
            async with self._session.get(req_url, params=params) as response:
                if response.status == 404:
                    return None, f'User by name {username} has never been disciplined'
                elif response.status != 200:
                    return None, f'Encountered HTTP error {response.status} when checking for user {username}'
                return await response.json(), None
        except aiohttp.ClientConnectionError:
            return None, 'Unable to contact database'

    async def reaction_role_embed_create(self,
                                         message_snowflake: int,
                                         guild_snowflake: int,
                                         creating_member_snowflake: int,
                                         emoji_role_mapping: Dict[int, int]):
        """
        NOTE: mapping is emoji -> role

        :param message_snowflake:
        :param guild_snowflake: the guild in which this reaction role embed exists
        :param creating_member_snowflake:
        :param emoji_role_mapping:
        :return:
        """
        emoji_role_mapping_list = [
            {'emoji_snowflake': emoji, 'role_snowflake': role} for emoji, role in emoji_role_mapping.items()
        ]
        creation_data = {
            'message_snowflake': message_snowflake,
            'guild_snowflake': guild_snowflake,
            'creating_member_snowflake': creating_member_snowflake,
            'mappings': emoji_role_mapping_list
        }
        req_url = self._api_url + 'reaction/tracked-reaction-embed/'
        try:
            async with self._session.post(req_url, json=creation_data) as response:
                if response.status != 201:
                    return None, f'Encountered an HTTP error creating at {req_url}: {response.status}'
                return await response.json(), None
        except aiohttp.ClientConnectionError:
            return None, 'Unable to contact database'

    async def reaction_role_embed_get(self, message_snowflake: int, guild_snowflake: int):
        """

        :param message_snowflake:
        :param guild_snowflake:
        :return:
        """
        req_url = self._api_url + f'reaction/tracked-reaction-embed/{message_snowflake}/'
        try:
            async with self._session.get(req_url, params={'guild_snowflake': guild_snowflake}) as response:
                if response.status != 200:
                    return None, f'Encountered an HTTP error getting at {req_url}: {response.status}'
                data = await response.json()
                try:
                    mappings = data['mappings']
                except KeyError as e:
                    return None, f'Encountered formatting error getting at {req_url}: {e}'
                data['mappings'] = {m['emoji_snowflake']: m['role_snowflake'] for m in mappings}
                return data, None
        except aiohttp.ClientConnectionError:
            return None, 'Unable to contact database'

    async def reaction_role_embed_list(self, guild_snowflake: int):
        """
        Gets the list of all reaction role embeds for the given guild.

        :param guild_snowflake: the guild for which all reaction role embeds should be retrieved
        :return: a tuple of (reaction embed list, None) on success, (None, error message) on failure.
        """
        req_url = self._api_url + 'reaction/tracked-reaction-embed/'
        try:
            async with self._session.get(req_url, params={'guild_snowflake': guild_snowflake}) as response:
                if response.status != 200:
                    return None, f'Encountered an HTTP error getting list at {req_url}: {response.status}'
                return await response.json(), None
        except aiohttp.ClientConnectionError:
            return None, 'Unable to contact database'

    async def reaction_role_embed_delete(self, guild_snowflake: int, message_snowflake: int) -> Optional[str]:
        """
        Attempts to delete the given reaction role embed.

        :param guild_snowflake: the guild under which the reaction role embed to delete exists
        :param message_snowflake: the snowflake of the reaction role embed message to delete
        :return: None on success, an error message on failure
        """
        req_url = self._api_url + f'reaction/tracked-reaction-embed/{message_snowflake}/'
        try:
            async with self._session.delete(req_url, params={'guild_snowflake': guild_snowflake}) as response:
                if response.status != 200:
                    return f'Encountered an HTTP error deleting at {req_url}: {response.status}'
            return None
        except aiohttp.ClientConnectionError:
            return 'Unable to contact database'

    async def reaction_role_embed_add_mappings(self,
                                               guild_snowflake: int,
                                               message_snowflake: int,
                                               emoji_role_mappings: Dict[int, int]):
        """

        :param guild_snowflake:
        :param message_snowflake:
        :param emoji_role_mappings:
        :return:
        """
        post_data = [{'emoji_snowflake': emoji, 'role_snowflake': role} for emoji, role in emoji_role_mappings.items()]
        req_url = self._api_url + f'reaction/tracked-reaction-embed/{message_snowflake}/add_mappings/'
        params = {'guild_snowflake': guild_snowflake}
        try:
            async with self._session.post(req_url, json=post_data, params=params) as response:
                if response.status != 201:
                    return f'Encountered an HTTP error adding mappings at {req_url}: {response.status}'
                return None
        except aiohttp.ClientConnectionError:
            return 'Unable to contact database'

    async def reaction_role_embed_remove_mappings(self,
                                                  guild_snowflake: int,
                                                  message_snowflake: int,
                                                  emoji_ids: List[int]):
        """

        :param guild_snowflake:
        :param message_snowflake:
        :param emoji_ids:
        :return:
        """
        req_url = self._api_url + f'reaction/tracked-reaction-embed/{message_snowflake}/remove_mappings/'
        params = {'guild_snowflake': guild_snowflake}
        try:
            async with self._session.post(req_url, json=emoji_ids, params=params) as response:
                if response.status != 200:
                    return f'Encountered an HTTP error removing mappings at {req_url}: {response.status}'
                return None
        except aiohttp.ClientConnectionError:
            return 'Unable to contact database'
