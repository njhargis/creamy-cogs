import string
from redbot.core import commands, Config, bank, errors, checks
from .blitzcrank import Blitzcrank

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
    async def leagueset(self, ctx: commands.Context):
        """Base command to manage League settings"""


    @leagueset.command()
    async def summoner(self, ctx: commands.Context, name: string):
        """This sets your summoner name to your account
        
        You must have a summoner name set to call !lol commands.
        """
        author = ctx.author

        # Your code will go here
        await self.config.member(author).summoner.set(name)

        await ctx.send(
            _("Value modified. Your summoner name is now {summoner_name}.").format(
                summoner_name=name
            )
        )

    # Change region (check vs approved)