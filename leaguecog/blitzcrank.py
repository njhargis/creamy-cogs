import asyncio
from lib2to3.pytree import Base
import logging
from xml.dom import NotFoundErr
import aiohttp
import discord
from redbot.core import Config

from leaguecog.mixinmeta import MixinMeta

log = logging.getLogger("red.creamy.cogs.league")


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

                    # Need to check if this summoner Id is already registered to someone in this guild..
                    user = self.config.member(member)
                    await user.summoner_name.set(name)
                    await user.puuid.set(pid)
                    await user.account_id.set(acctId)
                    await user.summoner_id.set(smnId)
                    await user.region.set(region.lower())

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

    async def check_games(self):
        # Find alert channel
        # Handle no channel set up.
        try:
            channelId = await self.config.alertChannel()
            channel = self.bot.get_channel(channelId)
            log.debug(f"Found channel {channel}")
        except BaseException as e:
            # Need to message owner if no channel is setup.
            log.exception("No channel setup to announce matches in." + str(e))

        # Loop through registered guild members
        registered_users = await self.config.all_members(channel.guild)
        for summoner in registered_users:
            data = registered_users[summoner]
            basePath, headers = await self.get_riot_url(data["region"])
            url = f"{basePath}spectator/v4/active-games/by-summoner/{data['summoner_id']}"
            async with self._session.get(url, headers=headers) as req:
                try:
                    data = await req.json()
                except aiohttp.ContentTypeError:
                    data = {}

                if req.status == 200:
                    self.user_in_game()
                elif req.status == 404:
                    self.user_is_not_in_game()
                elif req.status == 401:
                    # Need to raise token error
                    self.token_unauthorized()
                else:
                    log.warning = ("Riot API request failed with status code {statusCode}").format(
                        statusCode=req.status
                    )

    async def user_in_game(self):
        # Need to implement
        print("foo")

    async def user_is_not_in_game(self):
        # Need to implement
        print("foo")

    async def token_unauthorized():
        # Need to implement
        print("foo")
