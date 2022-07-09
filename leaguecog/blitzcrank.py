import asyncio
import logging
import aiohttp
import discord
from redbot.core import Config

from leaguecog.mixinmeta import MixinMeta

log = logging.getLogger("red.creamy-cogs.leaguecog")


class Blitzcrank(MixinMeta):
    """
    'The time of man has come to an end.'

    This class is responsible for:
        1) handling the token for Riot API.
        2) grabbing and pulling data from Riot API.
    """

    async def get_riot_url(self, region):
        """
        Given a region returns a Riot API url.

        ex. set API key for league with:
            [p]set api league api_key <key>
        """
        # If we've already gotten the API token, don't re-get it from the bot.
        if not self.api_key:
            db = await self.bot.get_shared_api_tokens("league")
            self.api_key = db["api_key"]

        # params = f"?api_key={self.api_key}"
        headers = {"X-Riot-Token": str(self.api_key)}
        basePath = f"https://{region}.api.riotgames.com/lol/"
        return (basePath, headers)

    async def simple_get(self, url):
        """
        Abstracts away simple GET HTTP calls using the cog-wide session.
        Should only be used if you don't want to handle failure/non-200 response codes.
        """
        async with self._session.get(url) as response:
            return await response.json()

    async def update_version(self):
        """This gets the most recent League API version, then updates our local list of champions"""
        version = await self.simple_get("https://ddragon.leagueoflegends.com/api/versions.json")
        if not self.champ_api_version:
            self.champ_api_version = version
            self.champlist = await self.simple_get(
                f"http://ddragon.leagueoflegends.com/cdn/{version[0]}/data/en_US/champion.json"
            )
        else:
            return

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
            currMsg = f"Region {region.upper()} not found. Available regions:\n" + ", ".join(
                [r.upper() for r in self.regions.keys()]
            )

        else:
            # build the url as an f-string, can double-check 'name' in the console
            basePath, headers = await self.get_riot_url(region)
            url = f"{basePath}summoner/v4/summoners/by-name/{name}".format()
            log.debug(f"url == {url}")
            async with self._session.get(url, headers=headers) as req:
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
                        currMsg = (
                            f"Summoner '{name}' does not exist in the region {region.upper()}."
                        )
                    elif req.status == 401:
                        currMsg = "Your Riot API token is invalid or expired."
                    else:
                        currMsg = f"Riot API request failed with status code {req.status}"

        finally:
            embed = await self.build_embed(title=currTitle, msg=currMsg, _type=currType)
            await message.edit(content=ctx.author.mention, embed=embed)

    async def check_games(self):  # noqa: C901
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
                    basePath, headers = await self.get_riot_url(region)
                    url = f"{basePath}spectator/v4/active-games/by-summoner/{smn}".format()
                    log.debug(f"url == {url}")
                    async with self._session.get(url, headers=headers) as req:
                        try:
                            data = await req.json()
                        except aiohttp.ContentTypeError:
                            data = {}
                        # They are in a game.
                        if req.status == 200:
                            # Only care about games on Summoner's Rift
                            if data["gameMode"] == "CLASSIC":
                                # If it is a custom, only care if 10 non-bots.
                                playerCount = 0
                                if data["gameType"] == "CUSTOM_GAME":
                                    for participant in data["participants"]:
                                        if not participant["bot"]:
                                            playerCount += 1
                                # FOR DEV TESTING IN CUSTOMS 1v0, swap comment out line below.
                                if (data["gameType"] == "MATCHED_GAME") or (
                                    data["gameType"] == "CUSTOM_GAME"
                                ):
                                    # if (data["gameType"] == "MATCHED_GAME") or (data["gameType"] == "CUSTOM_GAME" and playerCount == 10):
                                    # Use combination of gameid + smn id to add to current active game list if not in there already.
                                    alreadyTracked = False
                                    # This could be more DRY as it is repeated below.
                                    # async with self.config.guild(channel.guild).live_games() as live_games:
                                    curr_live_games = await self.config.guild(
                                        channel.guild
                                    ).live_games()
                                    # Need to not post twice when someone is in a game.
                                    for active_game in curr_live_games:
                                        if active_game != {} and active_game["active"]:
                                            if (
                                                str(active_game["gameId"])
                                                + str(active_game["smnId"])
                                            ) == (str(data["gameId"]) + str(smn)):
                                                alreadyTracked = True
                                    log.debug("Done checking vs list of tracked games.")
                                    if not alreadyTracked:
                                        log.debug("Appending new live game")
                                        # We only care about info related to this specific summoner
                                        for participant in data["participants"]:
                                            if participant["summonerId"] == smn:
                                                thisSmnInfo = participant
                                        await self.config.guild(channel.guild).live_games.set_raw(
                                            str(data["gameId"]) + str(smn),
                                            value={
                                                "gameId": data["gameId"],
                                                "smnId": smn,
                                                "region": region,
                                                "startTime": data["gameStartTime"],
                                                "teamId": thisSmnInfo["teamId"],
                                                "active": True,
                                            },
                                        )
                                        champs = self.champlist["data"]
                                        for i in champs:
                                            loopChamp = champs[i]
                                            if str(loopChamp["key"]) == str(
                                                thisSmnInfo["championId"]
                                            ):
                                                champName = loopChamp["name"]
                                        await channel.send(
                                            (
                                                "Summoner {smnId} started a game on {postChampName}!"
                                            ).format(
                                                smnId=summoner["smnId"],
                                                postChampName=champName,
                                            )
                                        )
                                    else:
                                        log.debug("We are already tracking this game.")
                        else:
                            if req.status == 404:
                                log.debug("Summoner is not currently in a game.")
                                # This could be more DRY, see above.
                                curr_live_games = await self.config.guild(
                                    channel.guild
                                ).live_games()
                                for active_game in curr_live_games:
                                    smn_id = await self.config.guild(
                                        channel.guild
                                    ).live_games.get_raw(active_game, "smnId")
                                    if str(smn_id) == str(smn):
                                        await self.config.guild(
                                            channel.guild
                                        ).live_games.clear_raw(active_game)
                                        await channel.send(
                                            ("Summoner {smnId}'s game has ended!").format(
                                                smnId=smn_id
                                            )
                                        )

                            else:
                                # Handle this more graciously
                                log.warning = (
                                    "Riot API request failed with status code {statusCode}"
                                ).format(statusCode=req.status)
                else:
                    log.debug("Skipped record")
                    continue
