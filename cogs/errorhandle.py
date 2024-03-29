from discord.ext import commands
import discord
import traceback

from utils import template
import utils.errors as errors


class Error(commands.Cog):
    """Handles errors related to the bot."""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, (discord.ext.commands.errors.CommandNotFound, discord.errors.Forbidden)):
            return
        if isinstance(error, commands.CheckFailure):
            return await ctx.send(
                embed=template.error('You don\'t have permission to use this command'),
                reference=ctx.message
            )
        try:
            if isinstance(error.original, errors.CustomError):
                return await ctx.send(
                    embed=error.original.embed,
                    reference=ctx.message
                )
        except AttributeError:
            pass
        if isinstance(error, (commands.errors.MissingRequiredArgument, errors.MissingArgument)):
            msg = str(error) if str(error) else 'Missing required argument'
            await ctx.send(embed=template.error(msg))
        tb = traceback.format_exception(type(error), error, error.__traceback__)
        tb_str = ''.join(tb[:-1]) + f'\n{tb[-1]}'
        message = await self.bot.owner.send(embed=template.error(f'```{tb_str}```', ctx.message.jump_url))
        await ctx.channel.send(embed=template.error('Internal Error, report submitted.', message.jump_url))


async def setup(bot):
    await bot.wait_until_ready()
    await bot.add_cog(Error(bot))
