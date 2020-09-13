
import aiohttp


class BotBackendClient:
    def __init__(self, api_url: str = 'http://localhost:8000/api/'):
        self._api_url = api_url
        self._session = aiohttp.ClientSession()

    async def close(self):
        await self._session.close()

    async def discipline_type_get_list(self):
        return await self._session.get(self._api_url + 'discipline-type')
