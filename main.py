import asyncio
import json
import traceback

import discord
from discord.ext import tasks, commands

import mongodb
import parse_commands as parse
import discord_templates as template

with open('config.json', encoding='utf-8') as file:
    config = json.load(file)

instance = {
    'test': mongodb.TestCloud,
    'production': mongodb.Cloud
}[config['db_instance']]
collection = mongodb.Collection(instance)

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=commands.when_mentioned_or(config['prefix']), intents=intents)
owner = None


@bot.command(name='echo', aliases=['say', 'repeat', 'print'])
async def echo(ctx):
    await ctx.channel.send(parse.get_args(ctx.message.content, arg_delimiter=''))


@bot.command(name='embed')
async def embed(ctx):
    try:
        dict_ = json.loads(parse.get_args(ctx.message.content, arg_delimiter=''))
        embed_ = discord.Embed.from_dict(dict_)
        await ctx.send(embed=embed_)
    except (json.decoder.JSONDecodeError, TypeError) as error:
        return await ctx.send(embed=template.error(f'```{str(error)}```'))
    except discord.errors.HTTPException:
        correct_usage = {
            "title": "example title",
            "description": "example description",
            "footer": {
                "text": "footer text"
            },
            "fields": [
                {
                    "name": "field1",
                    "value": "field value 1"
                }
            ]
        }
        return await ctx.send(embed=template.error(f'incorrect format\n\n'
                                                   f'Correct example:```json\n{json.dumps(correct_usage, indent=4)}```'))


@bot.command(name='clear')
async def clear_threads(ctx):
    if ctx.author.id != 468631903390400527:
        return
    for thread in ctx.channel.threads:
        await thread.delete()


@bot.command(name='db')
async def db(ctx):
    message = '```json\n'
    for document in collection.find(None, True):
        document = json.dumps(document, indent=4, ensure_ascii=False)
        if len(message) + len(document) + 3 > 2000:
            await ctx.send(message+'```')
            message = '```json\n'
        message += '\n' + document
    await ctx.send(message + '```')


@bot.command(name='callvote')
async def callvote(ctx):
    """To be implemented"""
    pass


@bot.listen()
async def on_command_error(ctx, error):
    global owner
    if isinstance(error, discord.ext.commands.errors.CommandNotFound) or isinstance(error, discord.errors.Forbidden):
        return
    if not owner:
        owner = await bot.fetch_user(468631903390400527)
    tb = traceback.format_exception(type(error), error, error.__traceback__)
    tb_str = ''.join(tb[:-1]) + f'\n{tb[-1]}'
    message = await owner.send(embed=template.error(f'```{tb_str}```', ctx.message.jump_url))
    await ctx.channel.send(embed=template.error('```Internal Error, report submitted.```', message.jump_url))


@bot.event
async def setup_hook() -> None:
    await bot.load_extension('giveaways')
    await bot.load_extension('modmail')

if __name__ == '__main__':
    bot.run(config['token'])
