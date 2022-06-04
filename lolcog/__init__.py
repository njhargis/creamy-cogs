from .lolcog import LolCog


def setup(bot):
    bot.add_cog(LolCog(bot))