import time
import json

import discord
from discord.ext import tasks, commands
from pymongo.errors import DuplicateKeyError

from utils import template
from utils import mongodb as db
from utils import parse_commands as parse

with open('config.json', encoding='utf-8') as file:
    config = json.load(file)

async def setup(bot):
    await bot.wait_until_ready()
    await bot.add_cog(Disqualify(bot))

class Disqualify(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.guild = bot.get_guild(config['guild_id'])
        self.dq_role = self.guild.get_role(config['disqualified_role_id'])
        self.check_dq_end.start()
        # declaring to keep linter happy
        self.mod_log_channel = None
        self.log_channel = None

    async def cog_load(self):
        self.mod_log_channel = await template.get_channel(self.bot, config['mod_log_channel_id'])
        self.log_channel = await template.get_channel(self.bot, config['log_channel_id'])

    @commands.command(name='disqualify', aliases=['dq'])
    async def disqualify(self, ctx):
        """Adds disqualified role to a user for a certain amount of time

        Syntax:
            g!dq user ; duration ; [reason]

        Example Usage:
            g!dq 468631903390400527 ; 7d ; Entering R0000 (prize) without meeting requirements

        Parameters:
            user - can be user id, mention, tag, nickname
            duration - duration of the dq, takes 5 units s, m, h, d, w (seconds, minutes, hours, days, weeks)
            [reason] - reason for the dq
        """
        user_str, duration, reason, suppress_log = parse.get_args(ctx.message.content, return_length=4, required=2)

        seconds = template.to_seconds(duration)
        member = await template.get_user(ctx=ctx, user_id=user_str, user_str=user_str, member_only=True)
        await member.add_roles(self.dq_role)
        ending = int(time.time() + seconds)
        document = {
            '_id': str(member.id),
            'ending': ending
        }
        try:
            db.collection.dq.insert(document)
        except DuplicateKeyError:
            db.collection.dq.update(str(member.id), document)
            await ctx.reply(embed=template.warning(f'Disqualification duration overwritten'))
        message = f'{member.mention} has been disqualified until <t:{ending}> ' \
                  f'by **{ctx.author}**.'
        if reason:
            message += f'\n**Reason:\n{reason}**'
        if not suppress_log:
            await self.mod_log_channel.send(message)

    async def un_dq(self, member: discord.Member):
        try:
            await member.remove_roles(self.dq_role)
            await self.log_channel.send(f'User {member.mention} disqualification removed')
        except discord.HTTPException:
            await self.log_channel.send(embed=template.error(
                f'HTTPException when removing disqualification role from {member.mention}'
            ))
        db.collection.dq.delete(member.id)

    async def cog_check(self, ctx) -> bool:
        allowed = template.is_staff(ctx)
        if allowed:
            await self.bot.log_channel.send(embed=template.command_used(ctx))
        return allowed

    @tasks.loop(seconds=5)
    async def check_dq_end(self):
        documents = db.collection.dq.find(None, True)  # Returns all result in collection as list
        for document in documents:
            print(document['ending'] < time.time())
            if document['ending'] < time.time():
                member = await template.get_user(guild=self.guild, user_id=document['_id'])
                await self.un_dq(member)
