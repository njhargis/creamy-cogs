import discord
from redbot.core import commands, Config, bank, errors, checks
#from .blitzcrank import Blitzcrank

class LeagueCog(commands.Cog):
    """Interact with the League of Legends API to find out information about summoners,
    champions, and to wager on people's matches with economy credits.
    """

    default_guild_settings = {
        "LIVE_SUMMONERS": {},
        "REGION": "NA"
    }

    default_member_settings = {
        "summoner": "",
    }

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 8945225427)
        self.config.register_guild(**self.default_guild_settings)
        self.config.register_member(**self.default_member_settings)

    @commands.group()
    async def league(self, ctx: commands.Context):
        """Base command to interact with the League Cog."""

    @league.command(name="summoner")
    async def get_summoner(self, ctx: commands.Context, member: discord.Member = None):
        """Returns a user's summoner name.
        
        If you do not enter a username, returns your own.
        """
        if member is None:
            member = ctx.author

        name = await self.config.member(member).summoner()

        if name:
            await ctx.send(
                ("That user's summoner name is {summoner_name}.").format(
                    summoner_name = name
                )
            )
        else:
            await ctx.send(
                ("That user does not have a summoner name setup yet.")
            )

    @commands.group()
    async def leagueset(self, ctx: commands.Context):
        """Base command to manage League settings"""

    @leagueset.command(name="summoner")
    async def set_summoner(self, ctx: commands.Context, *, name: str = ""):
        """This sets your summoner name to your account
        
        You must have a summoner name set to call !lol commands.
        """
        author = ctx.author

        name = name.strip()

        await self.config.member(author).summoner.set(name)

        await ctx.send(
            ("Value modified. Your summoner name is now {summoner_name}.").format(
                summoner_name = name
            )
        )

    # Change region (check vs approved)