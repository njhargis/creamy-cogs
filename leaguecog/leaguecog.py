from abc import ABC
import asyncio
import logging
from typing import Optional

import aiohttp
import discord
from redbot.core import checks, commands, Config
from redbot.core.bot import Red
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.predicates import MessagePredicate, ReactionPredicate

from .blitzcrank import Blitzcrank
from .ezreal import Ezreal
from .zilean import Zilean


log = logging.getLogger("red.creamy-cogs.league")


class CompositeMetaClass(type(commands.Cog), type(ABC)):
    """
    This allows the metaclass used for proper type detection to
    coexist with discord.py's metaclass
    """

    pass


class LeagueCog(
    Blitzcrank,
    Ezreal,
    Zilean,
    commands.Cog,
    metaclass=CompositeMetaClass,
):
    """
    Interact with the League of Legends API to find out information about summoners,
    champions, and to wager on people's matches with economy credits.
    """

    default_global_settings = {
        "notified_owner_missing_league_key": False,
    }

    default_guild_settings = {
        "default_region": "NA",
        "alert_channel": "",
        "posted_games": [],
    }

    default_role_settings = {"mention": False}

    default_member_settings = {
        "summoner_name": "",
        "puuid": "",
        "summoner_id": "",
        "account_id": "",
        "region": "",
        "active_game": {},
        "poll_member_games": True,
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
        self.api_key = None
        self.regions = {
            # restructuring this as a nested dict avoids constructing extra
            #   lists and dictionaries any time we need region processing
            "na": {"ser": "na1", "emoji": "🇺🇸"},
            "euw": {"ser": "euw1", "emoji": "🇪🇺"},
            "eune": {"ser": "eun1", "emoji": "🇳🇴"},
            "lan": {"ser": "la1", "emoji": "🇲🇽"},
            "br": {"ser": "br1", "emoji": "🇧🇷"},
            "las": {"ser": "la2", "emoji": "🇦🇷"},
            "jp": {"ser": "jp1", "emoji": "🇯🇵"},
            "kr": {"ser": "kr", "emoji": "🇰🇷"},
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

            log.debug("Attempting to start loop..")
            # determine time between looping through users
            await self.calculate_cooldown()
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
            await self.config.notified_owner_missing_league_key.set(False)
            self.task = self.bot.loop.create_task(self._game_alerts())
            log.debug("Local key updated.")

    async def cog_before_invoke(self, ctx: commands.Context):
        await self._ready_event.wait()

    async def _game_alerts(self):
        """Loops every X seconds to see if list of registered summoners are in a game."""
        await self.bot.wait_until_ready()
        while True:
            # this is the main check games loop
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
    @commands.guild_only()
    @checks.mod_or_permissions(manage_channels=True)
    async def setup_cog(self, ctx: commands.Context):
        """
        Guides the user through setting up different cog settings

        NOTE this is in dire need of refactoring

        For example, I think it would be reasonable to define these predicates
        as different functions, as this would enable us to let users go back
        and reset different settings individually later on with something like
        "[p]league setup --region"
        """

        ### SET REGION ###
        region_embed = await Ezreal.build_embed(
            self,
            title="SETUP - REGION",
            msg="React with the flag that most closely represents your region",
        )
        region_msg = await ctx.send(embed=region_embed)
        region_emojis = [v["emoji"] for v in self.regions.values()]

        # set up a ReactionPredicate and interpret the response
        #   then index the server (ex. 'na1') and abbreviation (ex. 'na')
        start_adding_reactions(region_msg, region_emojis)
        region_pred = ReactionPredicate.with_emojis(region_emojis, region_msg, ctx.author)
        await ctx.bot.wait_for("reaction_add", check=region_pred)

        region_idx = region_pred.result
        region = [k for k in self.regions.keys()][region_idx]

        # set guild region
        await self.config.guild(ctx.guild).default_region.set(region.upper())

        # TODO remove reactions

        # edit the original embed and show the user what was selected
        region_embed = await Ezreal.build_embed(
            self, title="SETUP - REGION", msg=f"Region set to {region.upper()}"
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
            await self.config.guild(ctx.guild).poll_guild_games.set(True)

        # TODO remove reactions

        # edit the original embed and show the user what was selected
        polling_embed = await Ezreal.build_embed(
            self,
            title="SETUP - POLLING",
            msg=f"Polling live games set to {polling_pred.result}",
        )
        await polling_msg.edit(content=ctx.author.mention, embed=polling_embed)

        ### CHOOSE ANNOUNCEMENT CHANNEL ###
        # get a dict of all available text channels
        #   this way you can get names and ids in one loop

        text_channel_dict = {}
        for guild in self.bot.guilds:
            for channel in guild.text_channels:
                text_channel_dict[channel.name] = channel.id

        # if number of channels is <= 10, can use a reaction predicate with the number emojis
        #   otherwise, catch an IndexError for the list of emojis and let the user
        #       input the name or number of the channel they want to use

        msg = "What channel do you want to use for announcements?\n"
        if len(text_channel_dict) <= 10:
            # only get the number of emojis you need to number the channels
            number_emojis = ReactionPredicate.NUMBER_EMOJIS[: len(text_channel_dict)]

            msg += "React with the appropriate channel number:\n\n"

            # number the channels within the embed message with the emojis
            for emoji, channel in zip(number_emojis, text_channel_dict.keys()):
                msg += f"{emoji} {channel}\n"

            channel_embed = await Ezreal.build_embed(
                self,
                title="SETUP - ANNOUNCEMENT CHANNEL",
                msg=msg,
            )
            channel_msg = await ctx.send(embed=channel_embed)

            # set up a ReactionPredicate and index text_channel_dict based on response
            start_adding_reactions(channel_msg, number_emojis)
            channel_pred = ReactionPredicate.with_emojis(number_emojis, channel_msg, ctx.author)
            await ctx.bot.wait_for("reaction_add", check=channel_pred)

        else:
            # add code blocking for looks
            msg += "Input the appropriate channel number:\n```"
            for idx, ch in enumerate(text_channel_dict.keys()):
                msg += f"{idx}. {ch}\n"
            msg += "```"
            channel_embed = await Ezreal.build_embed(
                self,
                title="SETUP - ANNOUNCEMENT CHANNEL",
                msg=msg,
            )
            channel_msg = await ctx.send(embed=channel_embed)
            # make sure the response is an integer that corresponds to a channel
            #   but MessagePredicate will read these as strings, not ints
            channel_pred = MessagePredicate.contained_in(
                [str(i) for i in range(len(text_channel_dict))]
            )
            await ctx.bot.wait_for("message", check=channel_pred)

        # index the channel name and id from the dict
        channel_idx = channel_pred.result
        alert_channel_name = [k for k in text_channel_dict.keys()][channel_idx]
        alert_channel_id = text_channel_dict[alert_channel_name]

        # set the alert channel via channel id
        await self.config.guild(ctx.guild).alert_channel.set(alert_channel_id)

        # TODO remove reactions, or remove last message if had to get text input

        # edit the original embed and show the user which channel was selected
        channel_embed = await Ezreal.build_embed(
            self,
            title="SETUP - ANNOUNCEMENT CHANNEL",
            msg=f"Announcement channel set to #{alert_channel_name}",
        )
        await channel_msg.edit(content=ctx.author.mention, embed=channel_embed)

        return

    @league.command(name="summoner")
    @commands.guild_only()
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

    @league.command(name="set-summoner")
    @commands.guild_only()
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
        # re-calculate time between check games loops
        await self.calculate_cooldown()

    @league.command(name="toggle-polling")
    async def toggle_polling(self, ctx: commands.Context, name: str = "", bool: str = None):
        """This allows the user to toggle polling on/off for their account"""
        pass

    @commands.group()
    async def leagueset(self, ctx: commands.Context):
        """Base command to manage League settings"""

    @leagueset.command(name="other-summoner")
    @commands.guild_only()
    @checks.mod_or_permissions()
    async def set_other_summoner(
        self,
        ctx: commands.Context,
        member: discord.Member,
        name: str = "",
        region: str = None,
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
    @commands.guild_only()
    @checks.mod_or_permissions(manage_channels=True)
    async def set_channel(self, ctx: commands.Context):
        """
        Call this command in the channel you want announcements for new games in.

        Example:
            [p]leagueset channel
        """
        await self.config.alert_channel.set(ctx.channel.id)
        await ctx.send("Channel set.")

    @leagueset.command(name="enable-matches")
    @commands.guild_only()
    @checks.mod_or_permissions(manage_channels=True)
    async def enable_matches(self, ctx: commands.Context):
        """
        Call this command once channel is setup and you are ready for matches to begin polling.

        Example:
            [p]leagueset enable-matches
        """
        # Need some logic to make sure a channel is set before allowing this command to run.
        await self.config.guild(ctx.guild).poll_guild_games.set(True)
        await ctx.send("Match tracking enabled.")

    @leagueset.command(name="reset")
    @checks.is_owner()
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
    @checks.is_owner()
    async def update_version_data(self, ctx: commands.Context):
        """
        If League of Legends updates this will get new champion data.

        Example:
            [p]leagueset update
        """
        await self.update_version()
        await ctx.send("Version patched.")

    @leagueset.command(name="league-token")
    @checks.is_owner()
    async def league_token(self, ctx: commands.Context):
        """Explain how to get and set the Riot token."""
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
        ).format(
            command="`{}set api league api_key {}`".format(
                ctx.clean_prefix, ("<your_riot_api_key_here>")
            )
        )

        await ctx.maybe_send_embed(message)
