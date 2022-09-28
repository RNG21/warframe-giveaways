import asyncio
import json
import random
import re
import time
import traceback
from typing import List, Iterable, Union

import discord
from discord import User, Member, Reaction
from discord.ext import tasks, commands

from utils import template, mongodb, parse_commands as parse
from utils.bot_extension import BotExtension
from utils.errors import DuplicateUnit, DisallowedChars, NoPrecedingValue, NotUser

with open('config.json', encoding='utf-8') as file:
    config = json.load(file)

instance = {
    'test': mongodb.TestCloud,
    'production': mongodb.Cloud
}[config['db_instance']]
collection = mongodb.Collection(instance)


async def setup(bot: BotExtension):
    await bot.wait_until_ready()
    await bot.add_cog(Giveaways(bot))


class Giveaway(object):
    duration: int
    winners: int
    description: str
    holder: template.Holder
    display_holder: bool
    prize: str
    display_title: bool
    message: discord.Message
    row: str

    def __init__(
            self,
            duration: int = None,
            winners: int = None,
            description: str = None,
            holder: template.Holder = None,
            display_holder: bool = None,
            prize: str = None,
            display_title: bool = False,
            message: discord.Message = None,
            row: str = None
    ):
        self.duration = duration
        self.winners = winners
        self.description = description
        self.holder = holder
        self.display_holder = display_holder
        self.prize = prize
        self.display_title = display_title
        self.message = message
        self.row = row


class Giveaways(commands.Cog):
    check_end_interval = 15

    def __init__(self, bot: BotExtension):
        self.bot = bot
        self.pending_end = {}
        self.delete_giveaway = {}
        self.thread_channel = None

    @commands.command(name='edit_giveaway')
    async def edit_giveaway(self, ctx):
        """To be implemented"""
        pass

    @commands.command(name='reroll')
    async def reroll(self, ctx):
        """Just, yeah, reroll"""
        message_id, winner_amount = parse.get_args(ctx.message.content, return_length=2)
        if winner_amount is None:
            winner_amount = 1

        # Validate args
        if not message_id:
            return await ctx.send(embed=template.error('Missing argument: message id'))

        # Get message to retrieve reactions
        try:
            message = await ctx.fetch_message(message_id)
        except discord.errors.NotFound:
            return await ctx.send(embed=template.error('Given message does not exist in this channel'))

        # Find db record of giveaway
        document = collection.archive.find(message_id)
        if not document:
            return await ctx.send(embed=template.error(
                'Unable to find giveaway.\nNote: you can only reroll a giveaway after it has ended'
            ))
        # draw winner and send result
        winners = await draw_winner(
            reactions=message.reactions,
            bot_user=self.bot.user,
            winner_amount=winner_amount
        )

        # Extract giveaway title and description
        giveaway_title = message.embeds[0].title
        giveaway_description = message.embeds[0].description

        # Send result
        await self.send_result(
            channel=ctx.channel,
            holder=template.Holder(**document['holder']),
            giveaway_title=giveaway_title,
            giveaway_description=giveaway_description,
            winners=winners,
            jump_url=f'https://discord.com/channels/{document["path"]}'
        )

    @commands.command(name='start')
    async def start(self, ctx):
        """Starts a giveaway
        Starts a giveaway
        Syntax: !start duration ; winners ; description ; [title]

        Example usage:
            !start 3d4h ; 1w ; Ember Prime Set
            !start 3600 ; 5 ;; Ember Prime Set

        Parameters:
            duration - integer or digits followed by a unit.
                       Allowed units:
                       {s, m, h, d, w} (denoting to seconds, minutes, hours, days, weeks respectively)
            winners - amount of winners on the giveaway
            description - Description of the giveaway, this will be the prize if title is not provided
            title - the prize and title of the giveaway
        """
        # Validate channel type
        if isinstance(ctx.channel, discord.DMChannel):
            return await ctx.channel.send(content='Giveaway in a DM channel?!')

        # Initialise
        correct_usage = '!start 3d4h ; 1w ; Ember Prime Set'
        args = parse.get_args(ctx.message.content, return_length=4)
        giveaway = Giveaway()

        # Validate number of args given
        invalid = []
        valid = []
        for arg in args:
            if not arg:
                invalid.append(1)
            else:
                valid.append(arg)
        if len(invalid) > 1:
            return await ctx.channel.send(
                embed=template.error(
                    "Command requires at least 3 arguments `(duration, winners, text, [kwargs])`\n"
                    f"Found {len(valid)} arguments: `{valid}`\n"
                    f"Correct usage: `{correct_usage}`"
                )
            )

        duration, winners, description, kwargs = args

        # Define description
        giveaway.description = description.replace('\\n', '\n')

        # Compute and validate duration
        if duration.isdigit():
            duration = int(duration)
        else:
            try:
                duration = __to_seconds__(duration)
            except (DisallowedChars, DuplicateUnit, NoPrecedingValue) as error:
                return await ctx.channel.send(embed=template.error(str(error)))
        giveaway.duration = int(duration + time.time())

        # Find and validate winner amount
        if winners.isdigit():
            giveaway.winners = int(winners)
        else:
            winners_match = re.findall('^(\d*)w', winners)
            if not winners_match:
                return await ctx.channel.send(embed=template.error('Winner amount not found\n'
                                                                   f'Correct usage: {correct_usage}'))
            elif len(winners_match) > 1:
                return await ctx.channel.send(embed=template.error(f'Multiple winner amounts found: {winners_match}\n'
                                                                   f'Correct usage: {correct_usage}'))
            giveaway.winners = int(winners_match[0])

        # Find holder
        try:
            warnings_ = await self.__find_holder__(ctx, giveaway)
        except NotUser as error:
            return await ctx.channel.send(embed=template.error(str(error)))
        for warning in warnings_:
            await ctx.channel.send(embed=template.warning(warning))

        # Find prize
        __find_prize__(giveaway)
        if kwargs:
            giveaway.display_title = True
            giveaway.prize = kwargs
        if len(giveaway.prize) > 256:
            giveaway.prize = giveaway.prize[:256]
            await ctx.channel.send(
                content=ctx.author.mention,
                embed=template.warning('Length of prize restricted to 256 chars')
            )

        # Send giveaway
        try:
            giveaway.message = await ctx.channel.send(
                embed=template.running_giveaway(
                    unix=giveaway.duration,
                    winners=giveaway.winners,
                    holder=giveaway.holder,
                    description=giveaway.description,
                    prize=giveaway.prize,
                    display_title=giveaway.display_title
                )
            )
            await giveaway.message.add_reaction('🎉')
        except discord.errors.Forbidden:
            # Determine which permission is missing
            if giveaway.message is not None:
                delete_after = 60
                embed = template.warning(
                    f'I need `Add Reaction` permission at {ctx.channel.mention}.\n'
                    f'Please manually add reaction of 🎉 to [the message]({message.jump_url})'  # noqa | validated
                    f'\n\nThis warning message will be deleted <t:{int(time.time() + delete_after)}:R>'
                )

                await ctx.channel.send(
                    content=ctx.author.mention,
                    embed=embed,
                    delete_after=delete_after
                )
            else:
                return await ctx.author.send(
                    embed=template.error(f'I need `Send Messages` permission at {ctx.channel.mention}')
                )

        # Add to running giveaways if ending after self.check_end_interval minutes
        server_id, channel_id, message_id = giveaway.message.jump_url.split('/')[-3:]
        document = {
            '_id': message_id,
            'ending': giveaway.duration,
            'winners': giveaway.winners,
            'holder': {
                'mention': giveaway.holder.mention,
                'tag': giveaway.holder.tag,
                'string': giveaway.holder.string
            },
            'path': f'{server_id}/{channel_id}/{message_id}'
        }
        if giveaway.duration > self.check_end_interval * 60 + time.time():
            collection.insert(document)
        # else start process (and add entry to db for redundancy)
        else:
            collection.insert(document)
            asyncio.create_task(self.end_giveaway(document))

        try:
            await ctx.message.delete()
        except discord.errors.Forbidden:
            pass

    async def __find_holder__(self, ctx: commands.Context, giveaway: Giveaway) -> List[str]:
        """
        Determines the holder from a giveaway description

        :param ctx: commands.Context
        :param giveaway: giveaway object
        :return: List[Embed] warnings. modifies the giveaway object
        """
        # Initialise
        holder = template.Holder()

        # Find user mention/id/tag
        id_lengths = range(19, 16, -1)  # large to small to match the longest id first
        patterns = [
            '(<@\d{' + f'{id_lengths[-1]},{id_lengths[0]}' + '}>)',
            '(' + '|'.join([r'\d{' + str(id_) + '}' for id_ in id_lengths]) + ')',
            '(.{2,32}#\d{4})'
        ]
        pattern = '|'.join(f'(?:[\n_~*`]*contact(?::)? {pattern})' for pattern in patterns)
        re_match = re.search(pattern, giveaway.description, flags=re.IGNORECASE)

        # Set holder to author if none found
        if re_match is None:
            giveaway.display_holder = True
            holder.mention = ctx.author.mention
            holder.tag = str(ctx.author)
            holder.string = f'Hosted by: {holder.tag}'

        # Define holder.mention or holder.tag
        else:
            giveaway.display_holder = False
            mention, id_, tag = re_match.groups()
            if mention:
                holder.mention = mention
                span = re_match.span(1)
            elif id_:
                # Replace id with mention
                holder.mention = f'<@{id_}>'
                span = re_match.span(2)
            elif tag:
                holder.tag = tag
                span = re_match.span(3)
            holder.string = f'Contact {holder.tag} to claim your prize'

        # Get member object
        if holder.mention:
            user_id = holder.mention[2:-1]
        else:
            user_id = None

        member, warnings_ = await template.get_member(bot=self.bot, ctx=ctx, user_id=user_id, user_tag=holder.tag)

        # if member successfully retrieved:
        if (member is not None) and (not giveaway.display_holder):
            if warnings_:  # warning if member not in guild, will not be in user cache therefore display tag
                giveaway.description = giveaway.description[:span[0]] + str(member) + giveaway.description[span[1]:]
            else:
                giveaway.description = giveaway.description[:span[0]] + member.mention + giveaway.description[span[1]:]
            # Populate both holder.tag and holder.id
            holder.mention = member.mention
            holder.tag = str(member)

        giveaway.holder = holder
        return warnings_

    async def end_giveaway(self, document: dict):
        """

        :param document:
        :return:
        """
        # method might be called from different places, return if instance already exist
        if document['_id'] in self.pending_end:
            # redundancy, method may also be called again if failed to end in previous call
            if self.pending_end[document['_id']] + 10 > time.time():
                return
        self.pending_end[document['_id']] = document['ending']

        wait_duration = document['ending'] - time.time()
        if wait_duration > 0:
            await asyncio.sleep(wait_duration)

        # return if giveaway was deleted during above sleep
        if document['_id'] in self.delete_giveaway:
            __archive_giveaway__(document['_id'], document)
            return

        server_id, channel_id, message_id = [int(_id) for _id in document['path'].split('/')]
        jump_url = f'https://discord.com/channels/{document["path"]}'
        # Get channel
        try:
            channel = await template.get_channel(self.bot, channel_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException, discord.InvalidData) as error:
            __archive_giveaway__(document['_id'], document)
            return self.bot.owner.send(
                embed=template.error(
                    f'{type(error).__name__}\n```{document}```'
                    f'[Jump]({jump_url})'
                )
            )

        # Get giveaway message
        try:
            message = await channel.fetch_message(message_id)
        # if message not found try sending error message to channel
        except discord.NotFound:
            try:
                __archive_giveaway__(document['_id'], document)
                return await channel.send(
                    embed=template.error(
                        'Hmm I can\'t seem to find a giveaway that\'s supposed to end at this time\n'
                        f'Please report to `{str(self.bot.owner)}` if you believe this is the bot\'s fault.\n\n'
                        f'Debug info:\n```json\n{json.dumps(document, indent=4, ensure_ascii=False)}```'
                    )
                )
            # if no perm to send error message, send to owner
            except discord.Forbidden:
                __archive_giveaway__(document['_id'], document)
                return await self.bot.owner.send(
                    f'Forbidden on sending following error\n'
                    f'Giveaway not found\n```{document}```'
                )
        # Catch all other errors on fetching message
        except Exception as error:
            tb = traceback.format_exception(type(error), error, error.__traceback__)
            tb_str = ''.join(tb[:-1]) + f'\n{tb[-1]}'
            __archive_giveaway__(document['_id'], document)
            return await self.bot.owner.send(
                f'```json\n{json.dumps(document, indent=4, ensure_ascii=False)}```',
                embed=template.error(f'Failed to end giveaway\n```{tb_str}```')
            )

        # Edit giveaway message
        if len(message.embeds) > 0:
            embed = message.embeds[0]
            fields = embed.fields
            if fields is not None:
                for i, field in enumerate(fields):
                    if field.name == 'Ending:':
                        embed.set_field_at(i, name='Ended:', value=field.value)
            embed.colour = None
            await message.edit(embed=embed)
        else:
            __archive_giveaway__(document['_id'], document)
            return await channel.send(embed=template.no_winner(jump_url, '**Warning:**\nEmbed on giveaway was deleted'))

        # Determine winner
        winners = await draw_winner(message.reactions, self.bot.user, document['winners'])
        if not winners:
            __archive_giveaway__(document['_id'], document)
            return await channel.send(embed=template.no_winner(jump_url))

        # Extract giveaway title and description
        giveaway_title = message.embeds[0].title
        giveaway_description = message.embeds[0].description

        # Send result
        await self.send_result(
            channel=channel,
            holder=template.Holder(**document['holder']),
            giveaway_title=giveaway_title,
            giveaway_description=giveaway_description,
            winners=winners,
            jump_url=jump_url
        )
        __archive_giveaway__(document['_id'], document)

    async def wait_and_mention(self, mentions: Iterable[str], winner_id: int, ref_message: discord.Message = None):
        """"""

        def check(message):
            return message.author.id == winner_id

        response = await self.bot.wait_for('message', check=check, timeout=604800)
        await response.channel.send(''.join(mention for mention in mentions), reference=ref_message)

    async def __create_ticket__(
            self,
            winners: Iterable[Union[Member, User]],
            giveaway_title: str,
            giveaway_description: str,
            jump_url: str,
            holder: template.Holder):
        """Creates modmail ticket for a giveaway

        Parameters:
            winners: list of winners, creates 1 ticket for each user
            giveaway_title: title of the giveaway
            giveaway_description: description of the giveaway
            jump_url: url of the giveaway message
            holder: giveaway item holder
        """
        for winner in winners:
            _, message = await template.create_ticket(
                thread_channel=self.thread_channel,
                thread_name=f'{winner.name} | {winner.id}',
                user_id=winner.id,
                messages=[{
                    'content': f'<@{winner.id}>',
                    'embed': template.winner_guide(
                        prize=giveaway_title,
                        description=giveaway_description,
                        giveaway_link=jump_url,
                        holder_tag=holder.tag
                    )
                }],
            )
            asyncio.create_task(self.wait_and_mention(
                mentions=(holder.mention,),
                winner_id=winner.id,
                ref_message=message
            ))

    async def send_result(
            self,
            channel: discord.TextChannel,
            holder: template.Holder,
            giveaway_title: str,
            giveaway_description: str,
            winners: Iterable[Union[Member, User]],
            jump_url: str
    ):
        """Sends giveaway result and creates ticket if in giveaway channel

        Parameters:
            channel: the channel to send result in
            holder: item holder
            giveaway_title: title of the giveaway message
            giveaway_description: description of the giveaway message
            winners: list of winners
            jump_url: url of original giveaway message
        """
        create_thread = True if channel.id in config['giveaway_channels'] else False

        await channel.send(
            **template.giveaway_result(
                winners=[winner.mention for winner in winners],
                giveaway_title=giveaway_title,
                giveaway_description=giveaway_description,
                holder=holder,
                giveaway_link=jump_url,
                mention_users=not create_thread
            )
        )

        # Create thread for winner to contact holder
        if create_thread:
            await self.__create_ticket__(
                winners=winners,
                giveaway_title=giveaway_title,
                giveaway_description=giveaway_description,
                jump_url=jump_url,
                holder=holder
            )

    @tasks.loop(minutes=check_end_interval)
    async def check_giveaway_end(self):
        documents = collection.find(None, True)  # Returns all result in collection as list
        for document in documents:
            if document['ending'] < time.time() + self.check_end_interval * 60:
                asyncio.create_task(self.end_giveaway(document))

    async def cog_check(self, ctx):
        if ctx.author == ctx.guild.owner:
            return True

        for role in ctx.author.roles:
            if role.permissions.administrator:
                return True
            elif role.id in config['giveaway_role_ids']:
                return True

        return False

    async def setup(self):
        if config['modmail_channel_id']:
            self.thread_channel = await template.get_channel(self.bot, config['modmail_channel_id'])

    async def cog_load(self):
        asyncio.create_task(self.setup())
        self.check_giveaway_end.start()


def __unformat__(string):
    to_remove = ['_', '~', '*', '`']
    unformatted = string
    for str_ in to_remove:
        unformatted = unformatted.replace(str_, '')
    return unformatted


def __to_seconds__(duration: str) -> int:
    """

    :param duration: (str) string of time with units of s, m, h, d,w
    :return: (dict) message (str) -> ok/error message
                    seconds (int)
    """
    disallowed = re.findall('[^ 0-9smhdw]', duration.strip())
    if disallowed:
        if len(disallowed) == 1:
            disallowed = disallowed[0]
        raise DisallowedChars(f'Disallowed characters found in duration of giveaway: `{disallowed}`\n'
                              f'Must have digit(s) followed by s, m, h, d or w')

    TO_SECONDS_MULTIPLIER = {
        's': 1,
        'm': 60,
        'h': 3600,
        'd': 86400,
        'w': 604800
    }
    matched_units = {}
    seconds = 0
    matches = re.findall(f'(\d*)([{"".join([unit for unit in TO_SECONDS_MULTIPLIER])}])', duration, re.IGNORECASE)
    for match_ in matches:
        num, unit = match_
        if (not num) and unit:
            raise NoPrecedingValue('Unit must be immediately preceded by an integer\n'
                                   f'Found unit `{unit}` with no preceding integer')
        if unit in matched_units:
            raise DuplicateUnit('Cannot have more than 1 match of same unit in duration of giveaway\n'
                                f'Found: `{["".join(re_match) for re_match in matches]}`')
        else:
            matched_units[unit] = None
            seconds += int(num) * TO_SECONDS_MULTIPLIER[unit]

    return seconds


def __find_prize__(giveaway: Giveaway):
    """Tries figuring the prize"""
    pattern = '(?:(?:PC|(?:xbox one)|ps4|playstation|switch|xbox) \| (R\d{4})\n)?(?:(.*\n*|(?:.*\n)*))' \
              '(?:(?:\nrestrictions(?:.*\n)*)|' \
              '(?:\ndonated by(?::)? .*\n)|' \
              '(?:\ncontact(?::)? .*))'

    re_match = re.findall(pattern, __unformat__(giveaway.description.strip()), re.IGNORECASE)
    if re_match:
        row = re_match[0][0]
        prize = re_match[0][1].strip()
        giveaway.display_title = True
    else:
        row = None
        prize = giveaway.description

    giveaway.prize = prize
    giveaway.row = row

    return prize, re_match


def __archive_giveaway__(_id: int, document: dict = None):
    if not document:
        document = collection.find(_id)

    collection.delete(_id)
    collection.archive.insert(document)


async def draw_winner(reactions: List[Reaction], bot_user, winner_amount: int = 1) -> List[Union[User, Member]]:
    winners = []
    for reaction in reactions:
        if reaction.emoji == '🎉':
            reacted_users: List[Union[User, Member]]
            reacted_users = [user async for user in reaction.users()]
            while len(winners) < winner_amount:
                if len(reacted_users) == 0:
                    break
                random_index = random.randint(0, len(reacted_users) - 1)
                if reacted_users[random_index] == bot_user:
                    reacted_users.pop(random_index)
                    continue
                winners.append(reacted_users[random_index])
                reacted_users.pop(random_index)
    return winners


if __name__ == '__main__':
    pass
