from datetime import datetime
import discord
import logging

from .mixinmeta import MixinMeta


log = logging.getLogger("red.creamy-cogs.league")


class Ezreal(MixinMeta):
    """
    'Lot of good mages out there. None of them are this hot!'

    This class is responsible for handling chat interactions with Discord.
    """

    async def build_embed(self, title=None, msg=None, _type=None):
        embed = discord.Embed()

        if title:
            embed.title = title
        else:
            embed.title = "League of Legends Cog"

        # If this is passed an embed, update fields.
        #   Otherwise just insert the string.
        if isinstance(msg, discord.Embed):
            for field in msg.fields:
                embed.add_field(**field.__dict__)
        else:
            embed.description = msg

        # Handle types with various standard colors and messages
        GREEN = 0x00FF00
        RED = 0xFF0000
        GRAY = 0x808080

        if _type == "apiSuccess":
            embed.color = GREEN
        elif _type == "apiFail":
            embed.color = RED
            end = "Sorry, something went wrong!"
            embed.add_field(name="-" * 65, value=end)
        elif _type == "invalidRegion":
            embed.color = RED
        else:
            embed.color = GRAY

        return embed

    async def build_active_game(
        self, summoner_name, game_type, champ_name, team1, team2, timestamp
    ):
        log.debug("Building embed")
        version = self.champ_api_version
        embed = discord.Embed()
        embed.title = f"{summoner_name} has started a {game_type} game!"
        embed.color = 0x00FF00
        embed.set_thumbnail(
            url=f"http://ddragon.leagueoflegends.com/cdn/{version}/img/champion/{champ_name}.png"
        )
        teamComp1 = ""
        teamComp2 = ""

        # Turn teams into strings
        for champ in team1:
            teamComp1 = teamComp1 + str(team1[champ]) + " "
        for champ in team2:
            teamComp2 = teamComp2 + str(team2[champ]) + " "

        # If a team is empty (bots don't count), don't fail out.
        if team1:
            embed.add_field(name="Blue Team", value=teamComp1)
        else:
            embed.add_field(name="Blue Team", value="No teammates.")

        if team2:
            embed.add_field(name="Red Team", value=teamComp2)
        else:
            embed.add_field(name="Red Team", value="No teammates.")

        embed.timestamp = datetime.utcnow()

        log.debug("Returning embed")
        return embed

    async def build_end_game(self, summoner_name, champ_name, team1, team2):
        version = self.champ_api_version
        embed = discord.Embed()
        embed.title = f"{summoner_name}'s game has ended."
        embed.color = 0xFF0000
        embed.set_thumbnail(
            url=f"http://ddragon.leagueoflegends.com/cdn/{version}/img/champion/{champ_name}.png"
        )
        embed.timestamp = datetime.utcnow()
        return embed
