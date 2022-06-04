from redbot.core import commands
from .blitzcrank import Blitzcrank

class LolCog(commands.Cog):
    """Interact with the League of Legends API to find out information about summoners,
    champions, and to wager on people's matches with economy credits.
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self)
        self.stats = Blitzcrank(bot)

    @commands.command()
    async def lol(self, ctx):
        """This does stuff!"""
        # Your code will go here
        await ctx.send("I am alive 2!")