from discord.ext import commands

from utils import template


class BotExtension(commands.Bot):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.owner = None

    async def setup(self):
        await self.wait_until_ready()
        self.owner, _ = await template.get_member(bot=self, user_id=468631903390400527)
