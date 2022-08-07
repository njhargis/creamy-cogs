import asyncio
import logging

import aiohttp
import discord
from lib2to3.pytree import Base
from redbot.core import Config
from xml.dom import NotFoundErr

from .mixinmeta import MixInMeta


log = logging.getLogger("red.creamy-cogs.league")


class Blitzcrank(MixInMeta):
    """
    'The time of man has come to an end.'

    This class is responsible for:
        1) handling the token for Riot API.
        2) grabbing and pulling data from Riot API.
    """

    async def check_token(self):
        """logic to check token or message if not."""
        blocked = await self.config.notified_owner_missing_league_key()
        if not blocked:
            # If we've already gotten the API token, don't re-get it from the bot.
            if not self.api_key:
                try:
                    db = await self.bot.get_shared_api_tokens("league")
                    self.api_key = db["api_key"]
                except KeyError:
                    await self.token_expired_or_missing()

    async def get_riot_url(self, region):
        """Given a region returns a Riot API url."""
        await self.check_token()
        headers = {"X-Riot-Token": str(self.api_key)}
        basePath = f"https://{region}.api.riotgames.com/lol/"
        return (basePath, headers)

    async def token_expired_or_missing(self):
        """
        If the Riot token is expired or missing then message the bot owner.
        Cancel the looping match games, and flag that it's missing so we don't keep
        calling the Riot API.
        """
        log.error("Riot API token is missing or invalid!")
        message = (
            "To set the Riot API tokens, follow these steps:\n"
            "1. Go to this page: https://developer.riotgames.com\n"
            "2. Click *Login* in the top right, using your riot credentials.\n"
            "3. Click register product, and then register for a Personal API Key.\n"
            "*DO NOT REGISTER FOR A PRODUCTION API KEY*\n"
            "4. Agree to their terms (read them!)\n"
            "5. Enter your bot name in *Product Name*.\n"
            "6. Put a simple description in the product description:\n"
            'Something like: "My bot is a Discord bot build using Red that'
            " will leverage the league cog to poll when anyone in our small Discord"
            ' starts up a match, and then announce when they win or lose."\n'
            "7. Leave *Product Group* as Default Group.\n"
            "8. Don't enter anything into the *Product URL*\n"
            "9. Set 'League of Legends' as the *Product Game Focus*\n"
            "THIS APPLICATION CAN TAKE A WHILE (up to months) TO GET APPROVED BY RIOT.\n"
            "They do not notify you when it completes, so check back often by logging in "
            "to the portal and then clicking your name -> Apps in the top right.\n"
            "{command}"
            "\n\n"
            "Note: These tokens are sensitive and should only be used in a private channel\n"
            "or in DM with the bot.\n"
        ).format(command="`{}set api league api_key {}`".format("!", ("<your_riot_api_key_here>")))
        if self.task:
            self.task.cancel()
        try:
            await self.bot.send_to_owners(message)
            log.debug("Message sent.")
            await self.config.notified_owner_missing_league_key.set(True)
        except BaseException as e:
            log.debug(e)

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
            self.champ_api_version = version[0]
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
            region = self.regions[region.lower()]["ser"]

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
            if not basePath == "block":
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
                        elif req.status == 401 or req.status == 403:
                            currTitle = "Invalid Token"
                            currType = "apiFail"
                            currMsg = "Your Riot API token is invalid or expired."
                            await self.token_expired_or_missing()
                        else:
                            currTitle = "Unexpected Error"
                            currType = "apiFail"
                            currMsg = f"Riot API request failed with status code {req.status}"
            else:
                currTitle = "Invalid Token"
                currType = "apiFail"
                currMsg = "Your Riot API token is invalid or expired."
        finally:
            embed = await self.build_embed(title=currTitle, msg=currMsg, _type=currType)
            await message.edit(content=ctx.author.mention, embed=embed)

    async def check_games(self):
        # Find alert channel
        # Handle no channel set up.
        log.debug("Looping guilds.")
        guilds = await self.config.all_guilds()
        for guildId in guilds:
            guild = await self.bot.fetch_guild(guildId)
            poll_matches = await self.config.guild(guild).poll_games()
            if poll_matches:
                try:
                    channelId = await self.config.guild(guild).alert_channel()
                    channel = self.bot.get_channel(channelId)
                    log.debug(f"Found channel {channel}")
                except BaseException as e:
                    # Need to handle if no channel is setup.
                    log.exception("No channel setup to announce matches in." + str(e))
                # Loop through registered guild members
                registered_users = await self.config.all_members(guild=guild)
                log.debug("Looping members.")
                for key, user_data in registered_users.items():
                    member = await self.bot.get_or_fetch_member(guild, key)
                    user = await self.bot.get_or_fetch_user(member.id)
                    poll_user = await self.config.user(user).poll_user_games()
                    if poll_user:
                        basePath, headers = await self.get_riot_url(user_data["region"])
                        if not basePath == "block":
                            url = f"{basePath}spectator/v4/active-games/by-summoner/{user_data['summoner_id']}"
                            async with self._session.get(url, headers=headers) as req:
                                try:
                                    game_data = await req.json()
                                except aiohttp.ContentTypeError:
                                    game_data = {}
                                if req.status == 200:
                                    await self.user_in_game(member, user_data, game_data, channel)
                                elif req.status == 404:
                                    await self.user_is_not_in_game(member, user_data, channel)
                                elif req.status == 401 or req.status == 403:
                                    await self.token_expired_or_missing()
                                else:
                                    log.warning = (
                                        "Riot API request failed with status code {statusCode}"
                                    ).format(statusCode=req.status)
                        else:
                            await self.token_expired_or_missing()

    async def user_in_game(self, member: discord.Member, user_data, game_data, channel):
        log.debug("User is in an active game")
        if not user_data["active_game"]:
            log.debug("User was not in a game previously.")
            await self.start_game(member, user_data, game_data, channel)
        # We are already tracking a game on them.
        else:
            tracked_game_data = user_data["active_game"]
            if game_data["gameId"] == tracked_game_data["gameId"]:
                log.debug("Skipped record, as we are already tracking this game.")
            else:
                log.debug("They are in a different game than what we are tracking.")
                await self.end_game(member, user_data, channel)
                await self.start_game(member, user_data, game_data, channel)

    async def user_is_not_in_game(self, member: discord.Member, user_data, channel):
        # Need to implement
        if user_data["active_game"]:
            await self.end_game(member, user_data, channel)

    async def start_game(self, member: discord.Member, user_data, game_data, channel):
        log.debug("Seeing if duplicate game..")
        # There is a possible de-sync issue that a game can be found right after we end it due to Riot API.
        # This prevents us from posting it again.
        games = await self.config.guild(channel.guild).posted_games()
        if (str(game_data["gameId"]) + str(user_data["summoner_id"])) not in games:
            log.debug("Starting game.")
            if game_data["gameMode"] == "CLASSIC":
                # If it is a custom, only care if 10 non-bots.
                playerCount = 0
                if game_data["gameType"] == "CUSTOM_GAME":
                    for participant in game_data["participants"]:
                        if not participant["bot"]:
                            playerCount += 1
                # FOR DEV TESTING IN CUSTOMS <10 players, comment out line 3 of this if.
                if (game_data["gameType"] == "MATCHED_GAME") or (
                    game_data["gameType"] == "CUSTOM_GAME" and playerCount == 10
                ):
                    if game_data["gameType"] == "CUSTOM_GAME":
                        game_type = "custom"
                    elif game_data["gameQueueConfigId"] == 420:
                        game_type = "ranked solo/duo"
                    elif game_data["gameQueueConfigId"] == 440:
                        game_type = "ranked flex"
                    elif game_data["gameQueueConfigId"] in (400, 430):
                        game_type = "normal"
                    else:
                        game_type = "unknown type:" + str(game_data["gameQueueConfigId"])
                    champs = self.champlist["data"]
                    team100 = {}
                    team200 = {}
                    for participant in game_data["participants"]:
                        for i in champs:
                            loopChamp = champs[i]
                            if str(loopChamp["key"]) == str(participant["championId"]):
                                champId = loopChamp["id"]
                                champName = loopChamp["name"]
                                champKey = loopChamp["key"]
                                if participant["summonerId"] == user_data["summoner_id"]:
                                    liveChampName = champName
                                    liveChampId = champId
                                if participant["teamId"] == 100:
                                    team100[champKey] = champName
                                if participant["teamId"] == 200:
                                    team200[champKey] = champName
                    embed = await self.build_active_game(
                        user_data["summoner_name"],
                        game_type,
                        liveChampName,
                        liveChampId,
                        team100,
                        team200,
                        game_data["gameStartTime"],
                    )
                    message = await channel.send(embed=embed)
                    await self.config.member(member).active_game.set(
                        value={
                            "gameId": game_data["gameId"],
                            "startTime": game_data["gameStartTime"],
                            "active": True,
                            "messageId": message.id,
                            "guildId": message.guild.id,
                            "champName": liveChampName,
                            "champId": liveChampId,
                            "team100": team100,
                            "team200": team200,
                        },
                    )
                    async with self.config.guild(channel.guild).posted_games() as games:
                        games.append(str(game_data["gameId"]) + str(user_data["summoner_id"]))
                    log.debug("Set active game")
        else:
            log.debug("Skipped duplicate game.")

    async def end_game(self, member: discord.Member, user_data, channel):
        log.debug("Ending game...")
        message_id = await self.config.member(member).active_game.get_raw("messageId")
        champ_id = await self.config.member(member).active_game.get_raw("champId")
        sent_message = await channel.fetch_message(message_id)
        embed = await self.build_end_game(user_data["summoner_name"], champ_id)
        await sent_message.edit(embed=embed)
        await self.config.member(member).active_game.clear_raw()
