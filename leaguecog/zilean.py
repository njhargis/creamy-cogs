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
        """
        Counts up all of the users registered with [p]league set-summoner,
            and calculates how often to hit the API while avoiding hitting the cap.
        If no one has registered, counts registered users as 1.
            This way, effectively the default refresh_timer is 4.8 seconds.
        """
        log.debug("Calculating cooldown...")
        total_registered_users = 0
        guilds = await self.config.all_guilds()

        for guildId in guilds:
            guild = await self.bot.fetch_guild(guildId)
            poll_matches = await self.config.guild(guild).poll_games()
            if poll_matches:
                users_in_guild = await self.config.all_members(guild=guild)
            # get the length of the guild dictionary and add it to your total_registered_users
            total_registered_users += len(users_in_guild)

        # if no one has registered, set total_registered_users to 1
        #   this way, refresh_timer doesn't get set to 0 seconds
        if total_registered_users < 1:
            total_registered_users = 1

        # leave bandwidth for some non-looping functions like set-summoner
        #   and account for multiple requests in each loop
        overhead_ratio = 0.75
        reqs_per_loop = 3

        # calculate the refresh timer, and round it off to 2 decimal places

        #  ( 120 seconds * # of users * requests per loop )
        # -------------------------------------------------- = seconds between each loop
        #      (  100 requests * overhead ratio )

        cooldown = round(
            ((120 * total_registered_users * reqs_per_loop) / (100 * overhead_ratio)),
            2,  # round to 2 decimal places
        )
        await self.config.refresh_timer.set(cooldown)
        log.debug(
            f"total registered users = {total_registered_users}, refresh timer cooldown = {cooldown}s"
        )
