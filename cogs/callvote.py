from discord.ext import commands


async def setup(bot):
    await bot.wait_until_ready()
    await bot.add_cog(CallVote(bot))


class CallVote(commands.Cog):
    def __init__(self, bot: commands.Bot = None):
        self.bot = bot

    @commands.command(name='callvote')
    async def callvote(self, ctx: commands.Context, title, description, duration, *args):
        """Starts a poll

        Parameters:
            title - Title of the poll
            description - Description of the poll
            duration - Duration of the poll
            *args - vote options
        """


