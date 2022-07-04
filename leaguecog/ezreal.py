import logging
import discord
from leaguecog.mixinmeta import MixinMeta

log = logging.getLogger("red.creamy.cogs.league")

class Ezreal(MixinMeta):
    """
    'Lot of good mages out there. None of them are this hot!'

    This class is responsible for handling chat interactions with Discord.
    """

    async def build_embed(self, title, msg, _type):
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