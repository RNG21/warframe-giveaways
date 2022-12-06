import asyncio
import json
import traceback
import aiohttp
import logging

import discord
from discord.ext import tasks, commands

from utils import template, mongodb, parse_commands as parse
from utils.bot_extension import BotExtension

# load config
with open('config.json', encoding='utf-8') as file:
    config = json.load(file)

# define db
db_instance = {
    'test': mongodb.TestCloud,
    'production': mongodb.Cloud
}[config['db_instance']]
collection = mongodb.Collection(db_instance)

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
    command_prefix=commands.when_mentioned_or(config['prefix']),
    intents=discord.Intents.all(),
    http_trace=trace_config
)


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


@bot.command(name='clear')
async def clear_threads(ctx):
    """Clears all threads in channel"""
    if ctx.author.id != 468631903390400527:
        return
    for thread in ctx.channel.threads:
        await thread.delete()


@bot.command(name='db')
async def db(ctx):
    """Prints all documents in database"""
    message = '```json\n'
    for document in collection.find(None, True):
        document = json.dumps(document, indent=4, ensure_ascii=False)
        if len(message) + len(document) + 3 > 2000:
            await ctx.send(message+'```')
            message = '```json\n'
        message += '\n' + document
    await ctx.send(message + '```')


@bot.event
async def setup_hook():
    asyncio.create_task(bot.load_extension('cogs.giveaways'))
    asyncio.create_task(bot.load_extension('cogs.modmail'))
    asyncio.create_task(bot.load_extension('cogs.errorhandle'))
    asyncio.create_task(bot.setup())


if __name__ == '__main__':
    bot.run(config['token'])
