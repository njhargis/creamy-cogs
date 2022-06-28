import asyncio

import aiohttp
import discord
from redbot.core import Config


class Blitzcrank:
    # "The time of man has come to an end."
    # This class is responsible for:
    #   1) handling the token for Riot API.
    #   2) grabbing and pulling data from Riot API.
    # To-Do:
    #   Move all standard API call logic into one function to call
    #   Warn user with instructions on how to set API key if it is invalid.
    #   Catch and warn if they try to input summoner with space, no quotes.

    def __init__(self, bot):
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
            "pbe": "pbe1",
        }
        self.config = Config.get_conf(self, 8945225427)

    async def __unload(self):
        asyncio.get_event_loop().create_task(self._session.close())

    async def get_league_api_key(self):
        """
        Loads the key-value pair 'api_key': <key> for 'league'
        If no key is assigned, returns None

        ex. set API key for league with:
            [p]set api league api_key <key>
        """
        if not self.api:
            db = await self.bot.get_shared_api_tokens("league")
            self.api = db["api_key"]
            return self.api
        else:
            return self.api

    async def apistring(self):
        apikey = await self.get_league_api_key()
        if apikey is None:
            return False
        else:
            return f"?api_key={apikey}"

    async def build_embed(self, title, msg, _type):
        embed = discord.Embed()

        if title:
            embed.title = title
        else:
            embed.title = "League of Legends Cog"

        # If this is passed an embed, update fields.
        #   Otherwise just insert the string.
        if isinstance(msg, discord.Embed):
            for field in msg.fields:
                embed.add_field(**field.__dict__)
        else:
            embed.description = msg

        # Handle types with various standard colors and messages
        GREEN = 0x00FF00
        RED = 0xFF0000
        GRAY = 0x808080

        if _type == "apiSuccess":
            embed.color = GREEN
        elif _type == "apiFail":
            embed.color = RED
            end = "Sorry, something went wrong!"
            embed.add_field(name="-" * 65, value=end)
        elif _type == "invalidRegion":
            embed.color = RED
        else:
            embed.color = GRAY

        return embed

    async def get(self, url):
        async with self._session.get(url) as response:
            return await response.json()

    async def get_summoner_info(self, ctx, name, region):
        message = await ctx.send(
            f"Attempting to register you as '{name}' in {region.upper()}..."
        )
        apiAuth = await self.apistring()
        await asyncio.sleep(3)

        try:
            region = self.regions[region.lower()]

        except KeyError:
            currTitle = "Invalid Region"
            currType = "invalidRegion"
            currMsg = f"Region {region.upper()} not found. Available regions:\n" + ", ".join(
                [r.upper() for r in self.regions.keys()]
            )

        else:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://{region}.api.riotgames.com/lol/summoner/v4/summoners/by-name/{name}/{apiAuth}"
                ) as req:
                    try:
                        data = await req.json()
                    except aiohttp.ContentTypeError:
                        data = {}

                    if req.status == 200:
                        currTitle = "Registration Success"
                        currType = "apiSuccess"
                        pid, acctId, smnId = (
                            data["puuid"],
                            data["accountId"],
                            data["id"],
                        )
                        currMsg = (
                            f"Summoner now registered.\n"
                            f"**Summoner Name**: {name}\n"
                            f"**PUUID**: {pid}\n"
                            f"**AccountId**: {acctId}\n"
                            f"**SummonerId**: {smnId}"
                        )

                    else:
                        currTitle = "Registration Failure"
                        currType = "apiFail"
                        if req.status == 404:
                            currMsg = f"Summoner '{name}' does not exist in the region {region.upper()}."
                        elif req.status == 401:
                            currMsg = "Your Riot API token is invalid or expired."
                        else:
                            currMsg = (
                                f"Riot API request failed with status code {req.status}"
                            )

        finally:
            embed = await self.build_embed(title=currTitle, msg=currMsg, _type=currType)
            await message.edit(content=ctx.author.mention, embed=embed)
