import asyncio
import logging
from typing import Optional
import aiohttp
import discord
from abc import ABC
from redbot.core import commands, Config
from redbot.core.bot import Red

from .blitzcrank import Blitzcrank
from .ezreal import Ezreal


log = logging.getLogger("red.creamy.cogs.league")


class CompositeMetaClass(type(commands.Cog), type(ABC)):
    """
    This allows the metaclass used for proper type detection to
    coexist with discord.py's metaclass
    """

    pass


class LeagueCog(
    Blitzcrank,
    Ezreal,
    commands.Cog,
    metaclass=CompositeMetaClass,
):
    """
    Interact with the League of Legends API to find out information about summoners,
    champions, and to wager on people's matches with economy credits.
    """

    default_global_settings = {
        # We should dynamically calculate this based on registered summoners to not hit throttle limit.
        "refresh_timer": 30,
        "notified_owner_missing_league_key": False,
        "poll_games": False,
    }

    default_guild_settings = {
        "default_region": "NA",
        "live_games": {},
        "registered_summoners": [{}],
    }

    default_role_settings = {"mention": False}

    default_member_settings = {
        "summoner_name": "",
        "puuid": "",
        "summoner_id": "",
        "account_id": "",
        "region": "",
    }

    def __init__(self, bot: Red):
        self.bot: Red = bot
        self.config = Config.get_conf(self, 8945225427)
        self.config.register_global(**self.default_global_settings)
        self.config.register_guild(**self.default_guild_settings)
        self.config.register_role(**self.default_role_settings)
        self.config.register_member(**self.default_member_settings)

        self.champ_api_version = None

        self._session = aiohttp.ClientSession()
        self.champlist = None
        self.api = None
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

        self.task: Optional[asyncio.Task] = None
        self._ready_event: asyncio.Event = asyncio.Event()
        self._init_task: asyncio.Task = self.bot.loop.create_task(self.initialize())

    async def initialize(self) -> None:
        """Should be called straight after cog instantiation."""
        await self.bot.wait_until_ready()
        try:
            log.debug("Updating Riot API Version...")
            # We need to run this more often, but not sure when.
            await self.update_version()
            if await self.config.poll_games():
                log.debug("Attempting to start loop..")
                self.task = self.bot.loop.create_task(self._game_alerts())
        except Exception as error:
            log.exception("Failed to initialize League cog:", exc_info=error)

        self._ready_event.set()

    @commands.Cog.listener()
    async def on_red_api_tokens_update(self, service_name, api_tokens):
        """This will listen for updates to api tokens and update cog instance of league token if it changed"""
        log.debug("Tokens updated.")
        if service_name == "league":
            self.api = api_tokens["api_key"]
            log.debug("Local key updated.")

    async def cog_before_invoke(self, ctx: commands.Context):
        await self._ready_event.wait()

    async def _game_alerts(self):
        """Loops every X seconds to see if list of registered summoners are in a game."""
        await self.bot.wait_until_ready()
        while True:
            log.debug("Checking games")
            await self.check_games()
            log.debug("Sleeping...")
            await asyncio.sleep(await self.config.refresh_timer())

    def cog_unload(self):
        """Close all sessions all pending async tasks when the cog is unloaded."""
        asyncio.get_event_loop().create_task(self._session.close())
        if self.task:
            self.task.cancel()

    @commands.group()
    async def league(self, ctx: commands.Context):
        """Base command to interact with the League Cog."""

    @league.command(name="setup")
    async def setup_cog(self, ctx: commands.Context):
        """
        Returns a user's summoner name.
        If you do not enter a username, returns your own.
        """
        # Set if they want to poll live games.
        # Set guild region
        # Set announcement channel
        # Setup Riot API key and request a permanent one.
        # Might be helpful example: https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/streams/streams.py#L122
        # You also could bot.send_to_owners if self.api is not set.
        return

    @league.command(name="summoner")
    async def get_summoner(self, ctx: commands.Context, member: discord.Member = None):
        """
        Returns a user's summoner name.
        If you do not enter a username, returns your own.

        Example:
            [p]league summoner @Bird#0000
            [p]league summoner
        """
        self = False
        if member is None:
            member = ctx.author
            self = True
        name = await self.config.member(member).summoner()
        region = await self.config.member(member).region()
        if not name and not self:
            await ctx.send("That user does not have a summoner name setup yet.")
        elif not name and self:
            await ctx.send("You do not have a summoner name setup yet.")
        elif name and not self:
            await ctx.send(f"That user's summoner name is {name}.")
        else:
            await ctx.send(f"Your summoner name is {name}, located in {region}.")

    @commands.group()
    async def leagueset(self, ctx: commands.Context):
        """Base command to manage League settings"""

    @leagueset.command(name="summoner")
    async def set_summoner(self, ctx: commands.Context, name: str = "", region: str = None):
        """
        This sets a summoner name to your Discord account.
        Names with spaces must be enclosed in "quotes". Region is optional.
        If you don't pass a region, it will use your currently assigned region.
        If you don't have a currently assigned region, it will use the default for the guild.

        Example:
            [p]leagueset summoner your_summoner_name NA
            [p]leagueset summoner "firstname lastname"
        """
        member = ctx.author
        name = name.strip()

        # If they did not pass a region, don't change their region if they have one set.
        # If they don't have one set, use the guild's default.
        if not region:
            region = await self.config.member(member).region()
            if not region:
                region = await self.config.guild(ctx.guild).default_region()

        # See if summoner name exists on that region.
        await self.get_summoner_info(ctx, name, member, region, True)

    @leagueset.command(name="other-summoner")
    async def set_other_summoner(
        self, ctx: commands.Context, member: discord.Member, name: str = "", region: str = None
    ):
        """
        This sets a summoner name to a Discord account. This should be deprecated eventually, but helpful for testing multiple user's.
        Names with spaces must be enclosed in "quotes". Region is optional.
        If you don't pass a region, it will use your currently assigned region.
        If you don't have a currently assigned region, it will use the default for the guild.

        Example:
            [p]leagueset other-summoner your_summoner_name @Bird#0000 NA
            [p]leagueset other-summoner "firstname lastname" @Bird#0000 na
        """
        name = name.strip()

        # If they did not pass a region, don't change their region if they have one set.
        # If they don't have one set, use the guild's default.
        if not region:
            region = await self.config.member(member).region()
            if not region:
                region = await self.config.guild(ctx.guild).default_region()

        # See if summoner name exists on that region.
        await self.get_summoner_info(ctx, name, member, region, False)

    @leagueset.command(name="channel")
    async def set_channel(self, ctx: commands.Context):
        """
        Call this command in the channel you want announcements for new games in.

        Example:
            [p]leagueset channel
        """
        await self.config.alertChannel.set(ctx.channel.id)
        await ctx.send("Channel set.")

    @leagueset.command(name="enable-matches")
    async def enable_matches(self, ctx: commands.Context):
        """
        Call this command once channel is setup and you are ready for matches to begin polling.

        Example:
            [p]leagueset enable-matches
        """
        await self.config.poll_games.set(True)
        await ctx.send("Match tracking enabled.")
        self.task = self.bot.loop.create_task(self._game_alerts())

    @leagueset.command(name="reset")
    async def reset_guild(self, ctx: commands.Context):
        """
        This clears out the database for the cog.
        Should be deprecated, for development use only.

        Example:
            [p]leagueset reset
        """
        await self.config.clear_all()
        await ctx.send("Data cleared.")

    @leagueset.command(name="update")
    async def update_version_data(self, ctx: commands.Context):
        """
        If League of Legends updates this will get new champion data.

        Example:
            [p]leagueset update
        """
        await self.update_version()
        await ctx.send("Version patched.")
