import asyncio
import logging

from .mixinmeta import MixinMeta


log = logging.getLogger("red.creamy-cogs.league")


class Zilean(MixinMeta):
    """
    'All in good time.'

    This class dynamically calculates refresh time for the bot
        based on registered summoners, so as to not hit throttle limit:
            *  20 requests every 1 seconds(s)
            *  100 requests every 2 minutes(s)

    Note that the API token is used for the whole bot,
        so if the bot is in multiple guilds, you have to take into account
            total registered users across all guilds.

    """

    # The goal here to calculate the interval at leaguecog init
    #   and then every time it loops through all the users
    #       this will pick up new users that registered during
    #           the last sleep window
    async def calculate_cooldown(self):
        total_registered_users = 0
        guilds = await self.config.all_guilds()

        log.info(f"guilds == {guilds}")

        for guildId in guilds:
            guild = await self.bot.fetch_guild(guildId)
            poll_matches = await self.config.guild(guild).poll_games()
            if poll_matches:
                registered_users_in_guild = await self.config.all_members(guild=guild)
            total_registered_users += registered_users_in_guild

        log.info(f"total_registered_users == {total_registered_users}")

        # leave bandwidth for some non-looping functions like set-summoner
        #   and account for multiple requests in each loop
        overhead_ratio = 0.75
        reqs_per_loop = 3

        cooldown = ((120 / (100 * overhead_ratio)) * total_registered_users) * reqs_per_loop
        log.info(f"cooldown == {cooldown}")
