from .leaguecog import LeagueCog


def setup(bot):
    bot.add_cog(LeagueCog(bot))
