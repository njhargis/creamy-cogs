from urllib.parse import urlencode
from redbot.core import Config
import aiohttp
import asyncio

class Blitzcrank:
    # "The time of man has come to an end."
    # This class is responsible for:
    #   1) handling the token for Riot API.
    #   2) grabbing and pulling data from Riot API.

    def __init__(self, bot):

        self.url = "https://{}.api.riotgames.com"
        self.api = None
        self.bot = bot
        self._session = aiohttp.ClientSession()
        self.regions = {
            "br": "br1",
            "eune": "eun1",
            "euw": "euw1",
            "jp": "jp1",
            "kr": "kr",
            "lan": "la1",
            "las": "la2",
            "na": "na1",
            "oce": "oc1",
            "tr": "tr1",
            "ru": "ru",
            "pbe": "pbe1"
        }
        self.config = Config.get_conf(self, 8945225427)
    
    async def __unload(self):
        asyncio.get_event_loop().create_task(self._session.close())
    
    # [p]set api league api_key
    async def get_league_api_key(self):
        if not self.api:
            db = await self.bot.get_shared_api_tokens("league")
            self.api = db['api_key']
            return self.api
        else:
            return self.api

    async def apistring(self):
        apikey = await self.get_league_api_key()
        if apikey is None:
            return False
        else:
            return "?api_key={}".format(apikey)

    async def get(self, url):
        async with self._session.get(url) as response:
            return await response.json()

    async def get_summoner_info(self, name, region : str):
        print(name)
        print(region)
        apistr = await self.apistring()
        request = self.url.format(self.regions[region.lower()]) + "/lol/summoner/v4/summoners/by-name/{}".format(name) + apistr
        js = await self.get(request)
        return js["puuid"], js ["accountId"], js["id"]
    
    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())
    
