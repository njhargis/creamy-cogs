import asyncio
import logging
from typing import Optional

import aiohttp
import discord
from abc import ABC
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.predicates import MessagePredicate, ReactionPredicate


from .blitzcrank import Blitzcrank
from .ezreal import Ezreal


log = logging.getLogger("red.creamy-cogs.leaguecog")


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
    }

    default_guild_settings = {
        "default_region": "NA",
        "poll_games": False,
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
            # restructuring this as a nested dict avoids constructing extra
            #   lists and dictionaries any time we need region processing
            "br": {"ser": "br1", "emoji": "🇧🇷"},
            "eune": {"ser": "eun1", "emoji": "🇳🇴"},
            "euw": {"ser": "euw1", "emoji": "🇪🇺"},
            "jp": {"ser": "jp1", "emoji": "🇯🇵"},
            "kr": {"ser": "kr", "emoji": "🇰🇷"},
            "lan": {"ser": "la1", "emoji": "🇲🇽"},
            "las": {"ser": "la2", "emoji": "🇦🇷"},
            "na": {"ser": "na1", "emoji": "🇺🇸"},
            "oce": {"ser": "oc1", "emoji": "🇦🇺"},
            "tr": {"ser": "tr1", "emoji": "🇹🇷"},
            "ru": {"ser": "ru", "emoji": "🇷🇺"},
            "pbe": {"ser": "pbe1", "emoji": "🇧"},
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
        """Cancel all pending async tasks when the cog is unloaded."""
        if self.task:
            self.task.cancel()

    @commands.group()
    async def league(self, ctx: commands.Context):
        """Base command to interact with the League Cog."""

    @league.command(name="setup")
    async def setup_cog(self, ctx: commands.Context):
        """
        Guides the user through setting up different cog settings

        NOTE this is in dire need of refactoring

        For example, I think it would be reasonable to define these predicates
        as different functions, as this would enable us to let users go back
        and reset different settings individually later on with something like
        "[p]league setup --region"
        """

        ### SETUP RIOT API KEY ### TODO

        ### SET REGION ###
        region_embed = await Ezreal.build_embed(
            self,
            title="SETUP - REGION",
            msg="React with the flag that most closely represents your region",
        )
        region_msg = await ctx.send(embed=region_embed)
        REGION_EMOJIS = [v["emoji"] for v in self.regions.values()]
        # set up a ReactionPredicate and interpret the response
        #   then index the server (ex. 'na1') and abbreviation (ex. 'na')
        start_adding_reactions(region_msg, REGION_EMOJIS)
        region_pred = ReactionPredicate.with_emojis(REGION_EMOJIS, region_msg, ctx.author)
        await ctx.bot.wait_for("reaction_add", check=region_pred)
        idx = region_pred.result
        ser = [v["ser"] for v in self.regions.values()][idx]
        region = [k for k in self.regions.keys()][idx]
        log.info(f"ser == {ser}, region == {region}")

        # TODO set guild region
        # TODO remove reactions

        # edit the original embed and show the user what was selected
        region_embed = await Ezreal.build_embed(
            self, title="Setup - REGION", msg=f"Region set to {region.upper()}"
        )
        await region_msg.edit(content=ctx.author.mention, embed=region_embed)

        ### ENABLE POLLING OR LEAVE OFF ###
        polling_embed = await Ezreal.build_embed(
            self, title="SETUP - POLLING", msg="Do you want to poll for live games?"
        )
        polling_msg = await ctx.send(embed=polling_embed)
        # set up a ReactionPredicate and interpret the response
        #   built-in method .yes_or_no() can interpret True/False
        start_adding_reactions(polling_msg, ReactionPredicate.YES_OR_NO_EMOJIS)
        polling_pred = ReactionPredicate.yes_or_no(polling_msg, ctx.author)
        await ctx.bot.wait_for("reaction_add", check=polling_pred)
        if polling_pred.result is True:
            # TODO set poll_games to True
            pass
        # TODO remove reactions
        # edit the original embed and show the user what was selected
        polling_embed = await Ezreal.build_embed(
            self, title="SETUP - POLLING", msg=f"Polling live games = {polling_pred.result}"
        )
        await polling_msg.edit(content=ctx.author.mention, embed=polling_embed)

        ### CHOOSE ANNOUCEMENT CHANNEL ###
        channel_embed = await Ezreal.build_embed(
            self,
            title="SETUP - ANNOUNCEMENT CHANNEL",
            msg=(
                "What channel do you want to use for announcements?\n"
                "Please enter the channel name:"
            ),
        )
        channel_msg = await ctx.send(embed=channel_embed)
        # set up a MessagePredicate to interpret user text input
        channel_pred = MessagePredicate.valid_text_channel(ctx)
        await ctx.bot.wait_for("message", check=channel_pred)
        log.info(f"channel_pred.result == {channel_pred.result}")
        # TODO purge the last message from the user
        # TODO Set announcement channel

        channel_embed = await Ezreal.build_embed(
            self,
            title="SETUP - ANNOUNCEMENT CHANNEL",
            msg=f"Annoucement channel set - #{channel_pred.result}",
        )
        await channel_msg.edit(content=ctx.author.mention, embed=channel_embed)

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
