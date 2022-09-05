from typing import Union, Iterable, Dict
import traceback

import discord

class Holder(object):
    def __init__(self, mention: str = None, tag: str = None):
        self.mention = mention
        self.tag = tag


def error(message: str, jump_url: str = '') -> discord.Embed:
    if jump_url:
        jump_url = f'\n[Jump]({jump_url})'
    return discord.Embed(
        title="Error",
        description=message+jump_url,
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
        description: str,
        holder: Holder,
        display_holder: bool,
        display_title: bool = False,
        prize: str = None)\
        -> discord.Embed:

    if not display_title:
        prize = None

    embed = discord.Embed(
        title=prize,
        description=description,
        colour=discord.Colour.blue()
    )

    if display_holder:
        embed.add_field(name='Hosted by: ', value=f'{holder.mention if holder.mention else holder.tag}\n')

    embed.add_field(name='Ending:', value=f'<t:{unix}:R> (<t:{unix}>)')

    text = f'{winners} winner'
    if winners > 1:
        text += 's'
    if holder.tag:  # Mentions don't work for
        if display_holder:
            text += f' | Hosted by: {holder.tag}'
        else:
            text += f' | Contact {holder.tag} to claim your prize'
    embed.set_footer(text=text)
    return embed


def giveaway_result(
        winners: Iterable[str],
        prize: str,
        holder: Holder,
        giveaway_link: str,
        mention_users: Union[Iterable[str], bool] = False)\
        -> Dict[str, Union[discord.Embed, str]]:
    """Return value to be used as kwargs for discord.abc.Messageable.send()"""

    if mention_users is True:
        mention_winners = ' '.join(winners)
    elif mention_users:
        mention_winners = ' '.join(mention_users)
    else:
        mention_winners = ''

    contact = holder.mention if holder.mention else holder.tag
    embed = discord.Embed.from_dict(
        {
            'color': 0x2ecc71,
            'title': f'Giveaway result',
            'fields': [
                {
                    'name': 'Prize:',
                    'value': f'{prize}',
                    'inline': True
                },
                {
                    'name': 'Jump to giveaway',
                    'value': f'[Jump to giveaway]({giveaway_link})',
                    'inline': True
                },
                {
                    'name': 'Winners:',
                    'value': '\n'.join(winners)
                }
            ],
            'footer': {
                'text': f'Item holder: {holder.tag}'
            }
        }
    )
    return {
        'content': mention_winners,
        'embed': embed
    }


def winner_guide(prize, giveaway_link, holder_tag):
    return discord.Embed.from_dict(
        {
            'color': 0x3498db,
            'title': 'Congratulations!',
            'description': f'You won: **{prize}**\n'
                           f'Send a message here to contact item holder to claim your prize',
            'fields': [
                {
                    'name': 'Jump to giveaway',
                    'value': f'[Jump to giveaway]({giveaway_link})'
                }
            ],
            'footer': {
                'text': f'Item holder: {holder_tag}'
            }
        }
    )


def no_winner(jump_url) -> discord.Embed:
    return discord.Embed(
        title='No winner found!',
        description=f'[Jump to giveaway]({jump_url})'
    )

async def create_thread(
        channel: discord.TextChannel,
        name: str,
        type_=discord.ChannelType.private_thread,
        add_users: Iterable[int] = (),
        mention_users: Union[Iterable[int], bool] = False,
        add_roles: Iterable[int] = (),
        start_msg: Union[str, discord.Embed] = None,
) -> discord.Thread:
    """Creates thread"""
    try:
        thread = await channel.create_thread(name=name, type=type_, invitable=False)
    except discord.HTTPException:
        thread = await channel.create_thread(name=name, type=discord.ChannelType.public_thread)

    edit_message = ''
    if mention_users is True:
        message = await thread.send(content=f'<@{"".join([str(id_) for id_ in add_users])}>')
    elif mention_users:
        content = f'<@{"".join([str(id_) for id_ in mention_users])}>'
        message = await thread.send(content=content)
        edit_message += content
    else:
        message = await thread.send(content=f'.')
        edit_message = f'<@{"".join([str(id_) for id_ in add_users])}>'

    if add_roles:
        edit_message += f'<@&{"".join([str(id_) for id_ in add_roles])}>'

    embed = None
    if type(start_msg) == str:
        edit_message += start_msg
    elif isinstance(start_msg, discord.Embed):
        embed = start_msg

    await message.edit(content=edit_message, embed=embed)
    return thread
