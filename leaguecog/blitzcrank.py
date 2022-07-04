import asyncio
import logging

import aiohttp
import discord
from redbot.core import Config

from leaguecog.abc import MixinMeta


log = logging.getLogger("red.creamy.cogs.league")


class Ezreal:
    """
    "Lot of good mages out there. None of them are this hot!"

    This class is reponsible for handling Discord Embed messages.
    """
    def __init__(self, ctx, title=None, msg=None, _type=None):
        self.ctx = ctx

        embed = discord.Embed()
        embed.title = title
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
        
        self.embed = embed

    async def send(self):
        message = await self.ctx.send("TODO Some on-brand message here...")
        await message.edit(
            content=self.ctx.author.mention, 
            embed=self.embed
        )


class Blitzcrank(MixinMeta):
    """
    "The time of man has come to an end."
    
    This class is responsible for:
        1) handling the token for Riot API.
        2) grabbing and pulling data from Riot API.
    """
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

    async def get(self, url):
        async with self._session.get(url) as response:
            return await response.json()

    async def get_summoner_info(self, ctx, name, member, region, isSelf):
        if isSelf:
            message = await ctx.send(
                f"Attempting to register you as '{name}' in {region.upper()}..."
            )
        else:
            message = await ctx.send(
                f"Attempting to register {member} as '{name}' in {region.upper()}..."
            )
        asyncio.sleep(3)
        apiAuth = await self.apistring()

        try:
            region = self.regions[region.lower()]

        except KeyError:
            # raise a KeyError for bad region, pass title, type, and message to build_embed()
            #    and send the author a formatted list of available regions
            currTitle = "Invalid Region"
            currType = "invalidRegion"
            currMsg = (
                f"Region {region.upper()} not found. Available regions:\n"
                + ", ".join([r.upper() for r in self.regions.keys()])
            )

        else:
            async with aiohttp.ClientSession() as session:
                # build the url as an f-string, can double-check 'name' in the console
                url = f"https://{region}.api.riotgames.com/lol/summoner/v4/summoners/by-name/{name}/{apiAuth}".format()
                log.info(f"url == {url}")

                async with session.get(url) as req:
                    try:
                        data = await req.json()
                    except aiohttp.ContentTypeError:
                        data = {}

                    if req.status == 200:
                        log.debug("200")
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
                        async with self.config.guild(ctx.guild).registered_summoners() as reg_smn:
                            # Need to check if this summoner Id is already in the list
                            reg_smn.append({"smnId": data["id"], "region": region.lower()})
                        await self.config.member(member).summoner_name.set(name)
                        await self.config.member(member).puuid.set(data["puuid"])
                        await self.config.member(member).account_id.set(data["accountId"])
                        await self.config.member(member).summoner_id.set(data["id"])
                        await self.config.member(member).region.set(region.lower())

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
            embed = Ezreal(ctx, title=currTitle, msg=currMsg, _type=currType)
            embed.send()


    async def check_games(self):
        # Find alert channel
        # Handle no channel set up.
        channelId = await self.config.alertChannel()
        channel = self.bot.get_channel(channelId)
        log.debug(f"Found channel {channel}")
        # Loop through registered summoners
        async with self.config.guild(channel.guild).registered_summoners() as registered_summoners:
            for summoner in registered_summoners:
                # Skip blank records
                if summoner != {}:
                    smn = summoner["smnId"]
                    region = summoner["region"]
                    log.debug(f"Seeing if summoner: {smn} is in a game in region {region}...")                       
                    apiAuth = await self.apistring()
                    url = f"https://{region}.api.riotgames.com/lol/spectator/v4/active-games/by-summoner/{smn}/{apiAuth}"
                    log.debug(f"url == {url}")
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            url
                        ) as req:
                            try:
                                data = await req.json()
                            except aiohttp.ContentTypeError:
                                data = {}
                            if req.status == 200:
                                # Create a list of combo gameid + smn id to add to current active game list if not in there already.
                                gameIds = []
                                log.debug("GameIds")
                                async with self.config.guild(channel.guild).live_games() as live_games:
                                   #Need to not post twice when someone is in a game.
                                   # for active_game in live_games:
                                     #   if active_game != {}:
                                     #       log.debug("Creating gameIds")
                                     #       gameIds.append(str(active_game["gameId"]) + str(active_game["smnId"]))
                                   # if str(data["gameId"]) + str(data["smnId"]) not in gameIds:
                                    log.debug("Appending new live game")
                                    live_games.append({"gameId": data["gameId"], "smnId": summoner["smnId"], "region": summoner["region"], "startTime": data["gameStartTime"]})
                                    message = await channel.send(
                                            ("Summoner {smnId} started a game!").format(
                                                smnId = summoner["smnId"]
                                            )
                                        )
                            else:
                                if req.status == 404:
                                    log.debug("Summoner is not currently in a game.")
                                else:
                                    # Handle this more graciously
                                    log.warning = ("Riot API request failed with status code {statusCode}").format(
                                        statusCode = req.status
                                    ) 
                else:
                    log.debug("Skipped record")
                    continue