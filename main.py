import asyncio
import json
import aiohttp
import logging

import discord
from discord.ext import commands

from utils import template
from utils import mongodb as db
from utils import parse_commands as parse
from utils.bot_extension import BotExtension
import config

# logging
async def on_request_start(_, __, params):
    log_string = f'Starting request | {params.method} | {params.url}'
    logging.getLogger('aiohttp.client').debug(log_string)
async def on_request_end(_, __, params):
    log_string = f'Request ended | {params.url}'
    logging.getLogger('aiohttp.client').debug(log_string)
async def on_request_chunk_sent(_, __, param):
    if param.chunk:
        log_string = f'request chunk sent | {param.chunk}'
        logging.getLogger('aiohttp.client').debug(log_string)
FORMAT = '%(asctime)s %(levelname)s %(filename)s | %(message)s'
logging.basicConfig(level=logging.DEBUG, format=FORMAT, filename=r'sent_requests.log')
trace_config = aiohttp.TraceConfig()
trace_config.on_request_start.append(on_request_start)
trace_config.on_request_end.append(on_request_end)
trace_config.on_request_chunk_sent.append(on_request_chunk_sent)

# define bot
bot = BotExtension(
    command_prefix=commands.when_mentioned_or(*config['prefix']),
    intents=discord.Intents.all(),
    http_trace=trace_config
)

@bot.command(name='die', aliases=['exit', 'quit'])
@commands.check(template.is_staff)
async def die(ctx):
    await ctx.channel.send('Exiting...')
    await ctx.bot.close()
    raise SystemExit

@bot.command(name='echo', aliases=['say', 'repeat', 'print'])
async def echo(ctx):
    await ctx.channel.send(parse.get_args(ctx.message.content, arg_delimiter=''))

@bot.command(name='embed')
async def embed(ctx):
    """Takes a json object and turns it into an embed"""
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
        return await ctx.send(embed=template.error(
            f'incorrect format\n\n'
            f'Correct example:```json\n{json.dumps(correct_usage, indent=4)}```'
        ))

@bot.command(name='sync')
@commands.check(template.is_staff)
async def sync_tree(ctx):
    await bot.tree.sync()
    await ctx.message.add_reaction('✅')

@bot.command(name='db')
@commands.check(template.is_staff)
async def db_(ctx, col=''):
    """Prints all documents in database"""
    message = '```json\n'
    if col not in ['c', 'a', 'd']:
        return await ctx.reply(embed=template.error(
            '```Requires 1 literal argument:\n'
            'c for active giveaways\n'
            'a for all giveaways\n'
            'd for active disqualifications\n\n'
            'Example:\ng!db c\n(this prints all active giveaways)```'
        ))
    collection = {
        'c': db.collection,
        'a': db.collection.archive,
        'd': db.collection.dq
    }[col]
    for document in collection.find(None, True):
        document = json.dumps(document, indent=4, ensure_ascii=False)
        if len(message) + len(document) + 3 > 2000:
            await ctx.send(message+'```')
            message = '```json\n'
        message += '\n' + document
    await ctx.send(message + '```')

@bot.command(name='re')
@commands.check(template.is_bot_owner)
async def reload_extension(ctx, extension: str):
    await bot.reload_extension(extension)
    await ctx.message.add_reaction('✅')

@bot.event
async def setup_hook():
    asyncio.create_task(bot.load_extension('cogs.giveaways'))
    asyncio.create_task(bot.load_extension('cogs.modmail'))
    asyncio.create_task(bot.load_extension('cogs.errorhandle'))
    asyncio.create_task(bot.load_extension('cogs.callvote'))
    asyncio.create_task(bot.load_extension('cogs.disqualify'))
    asyncio.create_task(bot.setup())


if __name__ == '__main__':
    bot.run(config.token)
