class Blitzcrank:
    # This class is responsible for grabbing and pulling data from Riot API.

    def __init__(self, bot):
        self.url = "https://{}.api.riotgames.com"
        self api = None
        self bot = bot
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

    async def _get_api_key(self):
        if not self.api:
            db = await self.bot.get_shared_api_tokens("riot")
            self.api = db['api_key']
            return self.api
        else:
            return self.api

    async def apistring(self):
        apikey = await self._get_api_key()
        if apikey is None:
            return False
        else:
            return "?api_key={}".format(apikey)

    async def get_summoner_puuid(self, name, region):
        apistr = await self.apistring()
        request = self.url.format(self.regions[region]) + "/lol/summoner/v4/summoners/by-name/{}".format(name) + apistr
        js = await self.get(request)
        return js["puuid"]
