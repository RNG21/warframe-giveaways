import json
import asyncio

import discord
from discord.ext import commands

from utils import template


async def setup(bot: commands.Bot):
    """for bot.load_extension"""
    if config['modmail_channel_id']:
        instance = ModMail(bot)
        bot.add_view(StartModmail(instance))
        await bot.add_cog(instance)


with open('config.json', encoding='utf-8') as file:
    config = json.load(file)

class StartModmail(discord.ui.View):
    def __init__(self, modmail_instance):
        super().__init__(timeout=None)
        self.modmail = modmail_instance

    @discord.ui.button(
        label='Contact staff',
        custom_id='persistent_view:contact_staff',
        emoji='📥'
    )
    async def contact_staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket, _ = await template.create_ticket(
            thread_channel=self.modmail.channel,
            thread_name=f'{interaction.user.name} | {interaction.user.id}',
            user_id=interaction.user.id,
            messages=[
                f'<@{interaction.user.id}>',
                str([f'<@&{id_}>' for id_ in config["mod_role_ids"]]),
                f'<@{interaction.user.id}>\nDescribe your issue here'
            ]
        )
        await interaction.response.send_message(f'Your ticket: <#{ticket.id}>', ephemeral=True)


class ModMail(commands.Cog):
    def __init__(self, bot: commands.Bot = None):
        self.bot = bot
        self.channel = None

    @commands.command(name='ticket')
    async def setup_ticket(self, ctx: commands.Context):
        """Sends a message with button, creates ticket on click"""
        embed = discord.Embed(
            colour=discord.Colour.green(),
            title='Contact staff',
            description='Click on the 📥 button below to open a ticket.'
        )
        await ctx.channel.send(embed=embed, view=StartModmail(self))
        return

    async def cog_check(self, ctx):
        if ctx.author == ctx.guild.owner:
            return True

        for role in ctx.author.roles:
            if role.permissions.administrator:
                return True

        return False

    async def setup(self):
        await self.bot.wait_until_ready()
        self.channel = await template.get_channel(self.bot, config['modmail_channel_id'])

    async def cog_load(self):
        asyncio.create_task(self.setup())
