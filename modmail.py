import json
import asyncio
from typing import Iterable, Union

import discord
from discord import app_commands
from discord.ext import tasks, commands

import discord_templates as template


async def setup(bot: commands.Bot):
    instance = ModMail(bot)
    bot.add_view(PersistentView(instance))
    await bot.add_cog(instance)


with open('config.json', encoding='utf-8') as file:
    thread_channel_id = int(json.load(file)['pickup_channel_id'])


class PersistentView(discord.ui.View):
    def __init__(self, modmail):
        super().__init__(timeout=None)
        self.modmail = modmail

    @discord.ui.button(label='Contact staff', custom_id='persistent_view:contact_staff')
    async def contact_staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket_id = await template.create_ticket(
            self.modmail.channel,
            interaction.user.id,
            f'<@{interaction.user.id}>\nSend a message here to contact staff'
        )
        await interaction.response.send_message(f'Send a message at <#{ticket_id}>', ephemeral=True)


class ModMail(commands.Cog):
    def __init__(self, bot: commands.Bot = None):
        self.bot = bot
        self.channel = None

    @commands.command(name='ticket')
    async def setup_ticket(self, interaction: discord.Interaction):
        embed = discord.Embed(
            colour=discord.Colour.green(),
            title='Contact staff',
            description='Click on the button below to contact staff'
        )
        await interaction.channel.send(embed=embed, view=PersistentView(self))
        return

    async def setup(self):
        await self.bot.wait_until_ready()
        self.channel = await template.get_channel(self.bot, thread_channel_id)

    async def cog_load(self):
        asyncio.create_task(self.setup())
