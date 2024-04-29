from discord.ext import commands

import config
from utils import template


class BotExtension(commands.Bot):
    """adds owner attribute (as a user object) to commands.Bot"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.owner = None
        self.log_channel = None

    async def setup(self):
        await self.wait_until_ready()
        self.owner = await template.get_user(bot=self, user_id=468631903390400527)
        if config.get('log_channel_id'):
            self.log_channel = await template.get_channel(bot=self, channel_id=config.log_channel_id)
