import discord
from redbot.core import commands, Config, bank, errors, checks
from redbot.core.bot import Red
from .blitzcrank import Blitzcrank

class LeagueCog(commands.Cog):
    """Interact with the League of Legends API to find out information about summoners,
    champions, and to wager on people's matches with economy credits.
    """

    default_guild_settings = {
        "default_region": "NA",
        "live_summoners": [],
        "registered_summoners": [],
    }

    default_member_settings = {
        "summoner_name": "",
        "puuid": "",
        "summoner_id": "",
        "account_id": "",
        "region": "NA"
    }

    def __init__(self, bot: Red):
        self.bot: Red = bot
        self.config = Config.get_conf(self, 8945225427)
        self.config.register_guild(**self.default_guild_settings)
        self.config.register_member(**self.default_member_settings)
        self.stats = Blitzcrank(bot)

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
            region = await self.config.member(member).region()
            await ctx.send(
                ("Your summoner name is {summoner_name}, located in{reg}.").format(
                    summoner_name = name,
                    reg = region
                )
            )

        else:
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
    async def set_summoner(self, ctx: commands.Context, name: str = "", region: str = None):
        """This sets your summoner name to your account. 
        
        Names with spaces must be enclosed in "quotes." Region is optional.
        If you don't pass a region, it will use your currently assigned region.
        If you don't have a currently assigned region, it will use the default for the guild.
        """
        author = ctx.author

        name = name.strip()

        # If they did not pass a region, don't change their region if they have one set.
        # If they don't have one set, use the guild's default.
        if not region:
            region = await self.config.member(author).region()
            if not region:
                region = await self.config.guild(ctx.guild).default_region()
        
        # See if summoner name exists on that region.
        puuid, acctId, summonerId = await self.stats.get_summoner_info(name, region)
        
        if not puuid:
            await ctx.send(
            ("Summoner name {summoner_name} is not valid, or does not exist on {reg} servers.").format(
                summoner_name = name,
                reg = region
            )
        )
        else:

            await self.config.member(author).summoner.set(name)
            await self.config.member(author).puuid.set(puuid)
            await self.config.member(author).summoner_id.set(acctId)
            await self.config.member(author).account_id.set(summonerId)
            await self.config.member(author).region.set(region)

            await ctx.send(
                ("Value modified. Your summoner name is now {summoner_name}.").format(
                    summoner_name = name
                )
            )

    # Change region (check vs approved)