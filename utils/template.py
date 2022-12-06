import json
import re
from typing import Union, Iterable, Dict, Tuple, List

import discord
from discord.ext import commands

from utils.errors import NotUser

with open('config.json', encoding='utf-8') as file:
    config = json.load(file)


class Holder(object):
    def __init__(self, mention: str = None, tag: str = None, string: str = None):
        self.mention = mention
        self.tag = tag
        self.string = string  # Contact <name> to claim your prize / Hosted by: <name>

    def __str__(self):
        return self.string


def error(message: str, jump_url: str = '') -> discord.Embed:
    if jump_url:
        jump_url = f'\n[Jump]({jump_url})'
    return discord.Embed(
        title="Error",
        description=message + jump_url,
        colour=discord.Colour.red()
    )


def warning(message: str) -> discord.Embed:
    return discord.Embed(
        title="Warning",
        description=message,
        colour=discord.Colour.yellow()
    )


def info(message: str) -> discord.Embed:
    return discord.Embed(
        title="Info",
        description=message,
        colour=discord.Colour.yellow()
    )


def running_giveaway(
        unix: int,
        winners: int,
        holder: Holder,
        description: str = None,
        prize: str = None) \
        -> discord.Embed:

    if (description is None) and (prize is None):
        raise Exception('description and prize must not both be None')

    embed = discord.Embed(
        title=prize,
        description=description,
        colour=discord.Colour.green()
    )

    embed.add_field(**__contact_type__(holder))
    embed.add_field(name='Ending:', value=f'<t:{unix}:R> (<t:{unix}>)')

    footer_text = f'{winners} winner'
    if winners > 1:
        footer_text += 's'
    if holder.tag:  # Mentions don't work for footer
        if str(holder):
            footer_text += f' | {holder}'
    embed.set_footer(text=footer_text)
    return embed


def giveaway_result(
        winners: Iterable[str],
        giveaway_title: str,
        giveaway_description: str,
        holder: Holder,
        giveaway_link: str,
        mention_users: Union[Iterable[str], bool] = False,
        reroll: bool = False) \
        -> Dict[str, Union[discord.Embed, str]]:
    """Return value to be used as kwargs for discord.abc.Messageable.send()"""

    # sets message content to winner arg if True
    # sets message content to mention_users if mention_users
    # sets message content to None if False
    if mention_users is True:
        mention_winners = ' '.join(winners)
    elif mention_users:
        mention_winners = ' '.join(mention_users)
    else:
        mention_winners = ''

    if reroll:
        title = 'Giveaway was rerolled'
        colour = discord.Colour.dark_blue()
    else:
        title = 'Giveaway result'
        colour = discord.Colour.blue()

    description = ''
    if giveaway_title:
        description += f'**{giveaway_title}**'
    if giveaway_description:
        description += f'\n{giveaway_description}'

    embed = discord.Embed(
        colour=colour,
        title=title,
        description=description
    )
    embed.add_field(**__contact_type__(holder))
    embed.add_field(name='Winners:', value='\n'.join(winners), inline=False)
    embed.add_field(name='Jump', value=f'[to giveaway]({giveaway_link})', inline=False)
    embed.set_footer(text=str(holder))

    return {
        'content': mention_winners,
        'embed': embed
    }


def __contact_type__(holder: Holder) -> dict:
    contact = holder.mention if holder.mention else holder.tag

    if not str(holder):
        raise Exception('__contact_type__ cannot be used when holder.string is empty or None')

    if re.search('Hosted by: .*', str(holder), re.IGNORECASE):
        return {'name': 'Hosted by:', 'value': contact, 'inline': True}
    elif re.search('Contact (.*) to claim your prize', str(holder), re.IGNORECASE):
        return {'name': 'Item Holder:', 'value': contact, 'inline': True}


def winner_guide(prize, description, giveaway_link, holder_tag):
    if description is None:
        description = ''
    if prize is None:
        prize = ''
        if description:
            description = f'**{description}**'
    if description:
        description += '\n\n'
    embed = discord.Embed(
        colour=discord.Colour.blue(),
        title=f"You won: {prize}",
        description=f"{description}"
                    "**Please tell us your ingame name and at what times you are available to trade**\n"
                    f"[Jump to giveaway]({giveaway_link})"
    )

    return embed


def no_winner(jump_url, message: str = '') -> discord.Embed:
    embed = discord.Embed(
        title='No winner found!',
        description=message + f'\n[Jump to giveaway]({jump_url})'
    )
    return embed


async def create_thread(
        channel: discord.TextChannel,
        name: str,
        messages: List[Union[str, discord.Embed, dict]],
        thread_type=discord.ChannelType.private_thread,
        auto_archive: int = 10080
) -> Tuple[discord.Thread, discord.Message]:
    """Creates thread"""
    try:
        thread = await channel.create_thread(
            name=name,
            type=thread_type,
            auto_archive_duration=auto_archive,
            invitable=False)
    except discord.HTTPException:
        thread = await channel.create_thread(
            name=name,
            type=discord.ChannelType.public_thread,
            auto_archive_duration=auto_archive
        )

    sent_message = await send_and_edit(thread, messages)

    return thread, sent_message


async def create_ticket(thread_channel: discord.TextChannel,
                        thread_name: str,
                        user_id: int,
                        messages: List[Union[str, discord.Embed, dict]],
                        delete_starter_message: bool = True,
                        auto_archive: int = 10080
                        ) -> Tuple[discord.Thread, discord.Message]:
    """Creates a ticket for user

    Parameters:
        thread_channel: text channel to create the ticket in
        thread_name: name of the thread
        user_id: id of the user creating the ticket
        messages: Initial messages on creating the thread, sends the first one and edits it into following ones.
            Sends only the last if thread already exists
        delete_starter_message: deletes public threads' starter message
        auto_archive: auto archive duration of the thread in minutes
    Returns:
        Tuple that consist of 2 elements, the thread and the start message
    """
    # Check if user already has ticket open
    threads = [
        *thread_channel.threads,
        *[thread async for thread in thread_channel.archived_threads(private=True)],
        *[thread async for thread in thread_channel.archived_threads(private=False)]
    ]
    for thread in threads:
        if str(user_id) in thread.name:  # If ticket already exist
            if thread_name != thread.name:
                # Change thread name if a different one provided
                # TODO: restrict usage cause discord doesn't like channel name changes
                await thread.edit(name=thread_name)

            message = await thread.send(**check_type(messages[-1]))
            return thread, message

    thread, message = await create_thread(
        channel=thread_channel,
        name=thread_name,
        messages=messages,
        auto_archive=auto_archive
    )
    if thread.starter_message and delete_starter_message:
        await thread.starter_message.delete()
    return thread, message


def check_type(message_: Union[str, discord.Embed, dict]) -> dict:
    """Checks the type of the message and returns suitable kwargs for .send"""
    if type(message_) == str:
        return {'content': message_}
    elif type(message_) == dict:
        return message_
    elif isinstance(message_, discord.Embed):
        return {'embed': message_}


async def send_and_edit(channel: discord.abc.Messageable, messages: List[Union[str, discord.Embed, dict]]):
    """Sends the first message in list and edits it into following elements in the list"""
    sent_message = await channel.send(**check_type(messages[0]))
    for message in messages[1:]:
        await sent_message.edit(**check_type(message))

    return sent_message


async def get_channel(bot: commands.Bot, channel_id: int):
    """Tries to get channel from cache then fetches from api if failed"""
    channel = bot.get_channel(channel_id)
    if channel is None:
        channel = await bot.fetch_channel(channel_id)
    return channel


async def get_member(
        bot: commands.Bot = None, ctx: commands.Context = None, guild: discord.Guild = None,
        user_id: int = None, user_tag: str = None)\
        -> Tuple[Union[discord.User, discord.Member, None], List[str]]:
    """Returns member or user object

    Requires (user_tag and ctx) or (user_id and (bot or ctx or guild))

    user_id and (bot or ctx or guild) -> Union[discord.User, discord.Member]
    user_tag and ctx -> Union[discord.User, discord.Member, None]
    """
    member_by_id = user_id and (ctx or guild)
    user_by_id = user_id and bot
    by_tag = user_tag and ctx
    if not (member_by_id or user_by_id or by_tag):
        raise Exception('Requires (user_tag and ctx) or (user_id and (bot or ctx or guild))')

    warnings_ = []

    if member_by_id:
        if ctx:
            guild = ctx.guild
        member = guild.get_member(user_id)
        if member is None:
            try:
                member = await guild.fetch_member(user_id)
            except discord.NotFound:
                if bot:
                    try:
                        member = await bot.fetch_user(user_id)
                        warnings_.append(f'`{str(member)}` is not a member of the server!')
                    except discord.NotFound:
                        raise NotUser(f'`{user_id}` is not user!')
                else:
                    warnings_.append(f'{user_id} is not member of the server!')

    elif user_by_id:
        try:
            member = await bot.fetch_user(user_id)
        except discord.NotFound:
            raise NotUser(f'`{user_id}` is not user!')
    elif by_tag:
        try:
            member = await commands.MemberConverter().convert(ctx, user_tag)
        except (commands.CommandError, commands.BadArgument):
            warnings_.append(f'Cannot convert `{user_tag}` to server member')
            member = None

    return member, warnings_
