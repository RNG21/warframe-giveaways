import re
import time
import asyncio
import json
import traceback
import random
from typing import List, Iterable

import discord
from discord.ext import tasks, commands

import discord_templates as template
import mongodb
import parse_commands as parse

collection = mongodb.Collection(mongodb.Cloud)
with open('config.json', encoding='utf-8') as file:
    thread_channel_id = json.load(file)['pickup_channel_id']


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaways(bot))


class DuplicateUnit(Exception):
    pass


class DisallowedChars(Exception):
    pass


class NoPrecedingValue(Exception):
    pass


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
    check_end_interval = 5
    bot: commands.Bot

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.owner = None
        self.setup_done = False
        self.pending_end = {}
        self.delete_giveaway = {}
        self.thread_channel = None

    @commands.command(name='edit_giveaway')
    async def edit_giveaway(self, ctx):
        pass

    @commands.command(name='start')
    async def start(self, ctx):
        """Starts a giveaway
        Parameters:
            duration - integer or digits followed by a unit.
                       Allowed units:
                       {s, m, h, d, w} (denoting to seconds, minutes, hours, days, weeks respectively)

        """
        # Validate channel type
        if isinstance(ctx.channel, discord.DMChannel):
            return await ctx.channel.send(content='Giveaway in a DM channel?!')
        # Validate user perm
        allowed = (ctx.author == ctx.guild.owner)
        for role in ctx.author.roles:
            if role.permissions.administrator:
                allowed = True
        allowed_role_ids = {
            487093541147901953: None,
            615739153010655232: None
        }
        for role in ctx.author.roles:
            if role.id in allowed_role_ids:
                allowed = True

        if not allowed:
            return await ctx.channel.send('no perm no start giveaway')

        # Initialise
        correct_usage = '!start 3d4h ; 1w ; Ember Prime Set'
        args = parse.get_args(ctx.message.content)
        giveaway = Giveaway()

        # Validate number of args
        if len(args) < 3:
            return await ctx.channel.send(
                embed=template.error(
                    "Command requires at least 3 arguments `(duration, winners, text, [kwargs])`\n"
                    f"Found {len(args)} arguments: `{args}`\n"
                    f"Correct usage: `{correct_usage}`"
                )
            )

        # Define description
        giveaway.description = args[2].replace('\\n', '\n')

        # Compute and validate duration
        duration = args[0]
        if duration.isdigit():
            duration = int(duration)
        else:
            try:
                duration = __to_seconds__(duration)
            except (DisallowedChars, DuplicateUnit, NoPrecedingValue) as error:
                return await ctx.channel.send(embed=template.error(str(error)))
        giveaway.duration = int(duration + time.time())

        # Find and validate winner amount
        if args[1].isdigit():
            giveaway.winners = int(args[1])
        else:
            winners = re.findall('^(\d*)w', args[1])
            if not winners:
                return await ctx.channel.send(embed=template.error('Winner amount not found\n'
                                                                   f'Correct usage: {correct_usage}'))
            elif len(winners) > 1:
                return await ctx.channel.send(embed=template.error(f'Multiple winner amounts found: {winners}\n'
                                                                   f'Correct usage: {correct_usage}'))
            giveaway.winners = int(winners[0])

        # Find holder
        try:
            warnings_ = await self.__find_holder__(ctx, giveaway)
        except template.NotUser as error:
            return await ctx.channel.send(embed=template.error(str(error)))
        for warning in warnings_:
            await ctx.channel.send(embed=template.warning(warning))

        # Find prize
        __find_prize__(giveaway)
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
            'row': giveaway.row,
            'ending': giveaway.duration,
            'prize': giveaway.prize,
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
        pattern = '(?:[\n_~*`]+contact(?::)? ' \
                  '(<@\d{' + f'{id_lengths[-1]},{id_lengths[0]}' + '}>)' \
                  '|(' + '|'.join([r'\d{' + str(id_) + '}' for id_ in id_lengths]) + '))' \
                  '|(?:[\n_~*`]+contact(?::)? (.{2,32}#\d{4}))'
        re_match = re.search(pattern, giveaway.description, flags=re.IGNORECASE )

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
            if not warnings_:  # warning if member not in guild, will not be in user cache therefore display tag
                giveaway.description = giveaway.description[:span[0]] + str(member) + giveaway.description[span[1]:] # noqa
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
            return self.owner.send(
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
                        f'Please report to `{str(self.owner)}` if you believe this is the bot\'s fault.\n\n'
                        f'Debug info:\n```json\n{json.dumps(document, indent=4, ensure_ascii=False)}```'
                    )
                )
            # if no perm to send error message, send to owner
            except discord.Forbidden:
                __archive_giveaway__(document['_id'], document)
                return await self.owner.send(f'Forbidden on sending following error\n'
                                             f'Giveaway not found\n```{document}```')
        # Catch all other errors on fetching message
        except Exception as error:
            tb = traceback.format_exception(type(error), error, error.__traceback__)
            tb_str = ''.join(tb[:-1]) + f'\n{tb[-1]}'
            __archive_giveaway__(document['_id'], document)
            return await self.owner.send(f'```json\n{json.dumps(document, indent=4, ensure_ascii=False)}```',
                                         embed=template.error(f'Failed to end giveaway\n```{tb_str}```'))

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
        winners = []
        for reaction in message.reactions:
            if reaction.emoji == '🎉':
                reacted_users = [user async for user in reaction.users()]
                while len(winners) < document['winners']:
                    if len(reacted_users) == 0:
                        break
                    random_index = random.randint(0, len(reacted_users) - 1)
                    if reacted_users[random_index] == self.bot.user:
                        reacted_users.pop(random_index)
                        continue
                    winners.append(reacted_users[random_index])
                    reacted_users.pop(random_index)
        if not winners:
            __archive_giveaway__(document['_id'], document)
            return await channel.send(embed=template.no_winner(jump_url))

        # Send result
        GIVEAWAY_CHANNELS = (
            718707589390663710,  # pc grand
            487801480380809227,  # pc general
            898527533191020544,  # pc riven
            703199049863528459,  # pc small
            620292174365327410,  # console
            732954678974873633  # botspam2 Test channel
        )
        create_thread = False
        if channel_id in GIVEAWAY_CHANNELS:
            create_thread = True
        holder = template.Holder(**document['holder'])
        __archive_giveaway__(document['_id'], document)

        await channel.send(
            **template.giveaway_result(
                winners=[winner.mention for winner in winners],
                prize=document['prize'],
                holder=holder,
                giveaway_link=jump_url,
                mention_users=not create_thread
            )
        )

        # Create thread for winner to contact holder
        if create_thread:
            thread_channel = await template.get_channel(self.bot, thread_channel_id)
            for winner in winners:
                thread_id = await template.create_ticket(
                    thread_channel=thread_channel,
                    user_id=winner.id,
                    start_msg={
                        'content': f'<@{winner.id}>',
                        'embed': template.winner_guide(
                            document['prize'],
                            f"https://discord.com/channels/{document['path']}",
                            holder.tag
                        )
                    }
                )
                asyncio.create_task(self.wait_and_mention((holder.mention,), thread_id))

    async def wait_and_mention(self, mentions: Iterable[str], thread_id: int):

        def check(message):
            return message.channel.id == thread_id

        response = await self.bot.wait_for('message', check=check)
        await response.channel.send(''.join(mention for mention in mentions))

    @tasks.loop(minutes=check_end_interval)
    async def check_giveaway_end(self):
        documents = collection.find(None, True)  # Returns all result in collection as list
        for document in documents:
            if document['ending'] < time.time() + self.check_end_interval * 60:
                asyncio.create_task(self.end_giveaway(document))

    async def setup(self):
        await self.bot.wait_until_ready()
        self.thread_channel = await template.get_channel(self.bot, thread_channel_id)
        self.owner = await self.bot.fetch_user(468631903390400527)

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
        raise DisallowedChars(f'Disallowed characters found: `{disallowed}`\n'
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
        try:
            matched_units[unit]  # noqa | Used for searching
            raise DuplicateUnit('Can not have more than 1 match of same unit\n'
                                f'Found: `{["".join(re_match) for re_match in matches]}`')
        except KeyError:
            matched_units[unit] = None
            seconds += int(num) * TO_SECONDS_MULTIPLIER[unit]

    return seconds  # noqa | Internal error if UnboundLocalError


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
    archive = mongodb.Collection(mongodb.CloudArchive)
    if not document:
        document = collection.find(_id)

    collection.delete(_id)
    archive.insert(document)


if __name__ == '__main__':
    pass
