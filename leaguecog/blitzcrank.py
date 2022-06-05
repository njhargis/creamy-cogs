from urllib.parse import urlencode
from redbot.core import Config
import aiohttp
import asyncio
import discord

class Blitzcrank:
    # "The time of man has come to an end."
    # This class is responsible for:
    #   1) handling the token for Riot API.
    #   2) grabbing and pulling data from Riot API.
    # To-Do:
    #   Need some check region logic
    #   Move all standard API call logic into one function to call
    #   Warn user with instructions on how to set API key if it is invalid.
    #   Catch and warn if they try to input summoner with space, no quotes.

    def __init__(self, bot):

        self.url = "https://{}.api.riotgames.com"
        self.api = None
        self.bot = bot
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

    async def get_summoner_info(self, ctx, name, region):
        message = await ctx.send(
            ("Attempting to register you as {smn_name} in {reg}...").format(
                smn_name = name,
                reg = region
            )
        )
        apiAuth = await self.apistring()
        await asyncio.sleep(3)
        async with aiohttp.ClientSession() as session:
            async with session.get(
                self.url.format(self.regions[region.lower()]) + "/lol/summoner/v4/summoners/by-name/{}".format(name) + apiAuth
            ) as req:
                try:
                    data = await req.json()
                except aiohttp.ContentTypeError:
                    data = {}
                
                if req.status == 200:
                    currTitle = "Registration Success"
                    currType = "apiSuccess"
                    currMsg = "Summoner now registered.\n **Summoner Name**: {smnName}\n **PUUID**: {pid}\n **AccountId**: {acctId}\n **SummonerId**: {smnId}".format(
                        smnName = name,
                        pid = data["puuid"],
                        acctId = data["accountId"],
                        smnId = data["id"]
                    )

                else:
                    currTitle = "Registration Failure"
                    currType = "apiFail"
                    if req.status == 404:
                        currMsg = "Summoner does not exist in the region."
                    elif req.status == 401:
                        currMsg = "Your Riot API token is invalid or expired."
                    else:
                        currMsg = ("Riot API request failed with status code {statusCode}").format(
                            statusCode = req.status
                        )
                    
                embed = await self.build_embed(title = currTitle, msg = currMsg, type = currType)
                await message.edit(content=ctx.author.mention, embed=embed)

    async def build_embed(self, title, msg, type):
        embed = discord.Embed()

        if title:
            embed.title = title
        else:
            embed.title = "League of Legends Cog"
        
        # If this is passed an embed, update fields
        # Otherwise just insert the string.
        if isinstance(msg, discord.Embed):
            for field in msg.fields:
                embed.add_field(**field.__dict__)
        else:
            embed.description = msg

        # Handle types with various standard colors and messages.
        if type == "apiSuccess":
            embed.color = 0x00FF00
        elif type == "apiFail":
            embed.color = 0xFF0000
            end = ("Sorry, something went wrong!")
            embed.add_field(name="-" * 65, value = end)
        else:
            embed.color = 0x808080
        
        return embed