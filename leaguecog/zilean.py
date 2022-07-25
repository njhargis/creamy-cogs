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

    Since the API token is used for the singular bot instance, it will
        take into acount total registered users across all guilds.

    NOTE overhead_ratio and reqs_per_loop can be changed to provide
        more or less overhead and adjust requests per check_games loop
            per summoner as needed.
    """

    async def calculate_cooldown(self):
        # start with total_registered_users = 1 else refresh timer
        #   will default to zero
        total_registered_users = 1
        guilds = await self.config.all_guilds()

        log.info(f"guilds == {guilds}")

        for guildId in guilds:
            log.info(f"guildId == {guildId}")
            guild = await self.bot.fetch_guild(guildId)
            poll_matches = await self.config.guild(guild).poll_games()
            log.info(f"poll_matches == {poll_matches}")
            if poll_matches:
                registered_users_in_guild = await self.config.all_members(guild=guild)
                log.info(f"registered_users_in_guild = {registered_users_in_guild}")
            total_registered_users += registered_users_in_guild

        log.info(f"total_registered_users == {total_registered_users}")

        # leave bandwidth for some non-looping functions like set-summoner
        #   and account for multiple requests in each loop
        overhead_ratio = 0.75
        reqs_per_loop = 3

        self.cooldown = round(
            ((120 / (100 * overhead_ratio)) * total_registered_users) * reqs_per_loop,
            2,  # decimal places
        )
        log.info(f"zilean cooldown == {self.cooldown}")
