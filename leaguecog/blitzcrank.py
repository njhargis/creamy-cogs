import asyncio
import logging
import aiohttp
import discord
from redbot.core import Config

from leaguecog.abc import MixinMeta

log = logging.getLogger("red.creamy.cogs.league")

class Blitzcrank(MixinMeta):
    """
    'The time of man has come to an end.'

    This class is responsible for:
       1) handling the token for Riot API.
       2) grabbing and pulling data from Riot API.
    """

    async def __unload(self):
        '''
        Close any sessions that are open if unloading the cog.
        '''
        asyncio.get_event_loop().create_task(self._session.close())

    async def get_riot_url(self, region):
        """
        Given a region returns a Riot API url.
        
        ex. set API key for league with:
            [p]set api league api_key <key>
        """
        # If we've already gotten the API token, don't re-get it from the bot.
        if not self.api:
            db = await self.bot.get_shared_api_tokens("league")
            self.api = db["api_key"]
        
        endOfPath = f"?api_key={self.api}"
        beginOfPath = f"https://{region}.api.riotgames.com/lol/"
        return (beginOfPath, endOfPath)

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
        await asyncio.sleep(3)

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
                beginOfPath, endOfPath = await self.get_riot_url(region)
                url = f"{beginOfPath}summoner/v4/summoners/by-name/{name}/{endOfPath}".format()
                log.debug(f"url == {url}")

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
            embed = await self.build_embed(title=currTitle, msg=currMsg, _type=currType)
            await message.edit(content=ctx.author.mention, embed=embed)

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
                    beginOfPath, endOfPath = await self.get_riot_url(region)
                    url = f"{beginOfPath}spectator/v4/active-games/by-summoner/{smn}/{endOfPath}".format()
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