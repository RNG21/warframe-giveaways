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
import utils.errors as errors

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
    message: discord.Message

    def __init__(
            self,
            duration: int = None,
            winners: int = None,
            description: str = None,
            holder: template.Holder = None,
            display_holder: bool = None,
            prize: str = None,
            message: discord.Message = None,
    ):
        self.duration = duration
        self.winners = winners
        self.description = description
        self.holder = holder
        self.display_holder = display_holder
        self.prize = prize
        self.message = message


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

    @commands.command(name='end')
    async def end(self, ctx):
        """Ends a giveaway before timer runs out

        Example usage:
            !gend 1049431042206990498

        Parameters:
            id_ - message id of the giveaway (not the result message)
        """

        message_id = parse.get_args(ctx.message.content, return_length=1)[0]
        document = collection.find(message_id)
        if document is None:
            raise errors.CustomError(f'No active giveaway with ID `{message_id}` found')
        document['ending'] = time.time()
        await self.end_giveaway(document)

    @commands.command(name='reroll')
    async def reroll(self, ctx):
        """Rerolls a giveaway

        Example usage:
            !greroll 1049431042206990498

        Parameters:
            id_ - message id of the giveaway (not the result message)
            [winner_amount] - amount of new winners
        """
        message_id, winner_amount = parse.get_args(ctx.message.content, return_length=2)
        if winner_amount is None:
            winner_amount = 1
        elif not winner_amount.isdigit():
            raise errors.CustomError(f'Winner amount must be integer, got `{winner_amount}` instead')
        else:
            winner_amount = int(winner_amount)

        # Validate args
        if not message_id:
            raise errors.CustomError('Missing argument: message id')

        # Find db record of giveaway
        document = collection.archive.find(message_id)
        if not document:
            raise errors.CustomError(f'Unable to find giveaway with id `{message_id}`.\n')

        # Get message to retrieve reactions
        channel = await template.get_channel(self.bot, document['path'].split('/')[1])
        try:
            message = await channel.fetch_message(message_id)
        except discord.errors.NotFound:
            raise errors.CustomError('Giveaway not found!')

        # draw winner and send result
        winners = await draw_winner(
            reactions=message.reactions,
            bot_user=self.bot.user,
            winner_amount=winner_amount
        )
        if not winners:
            return await ctx.channel.send(embed=template.no_winner(
                f'https://discord.com/channels/{document["path"]}'
            ))

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
            jump_url=f'https://discord.com/channels/{document["path"]}',
            reroll=True
        )

    @commands.command(name='start')
    async def start(self, ctx):
        """Starts a giveaway
        Syntax: !gstart duration ; winners ; title ; [description] ; [holder]

        Example usage:
            !gstart 3d4h ; 1w ; Weapon Slots
            !gstart 3600 ; 5 ;; Weapon Slots

        Parameters:
            duration - integer or digits followed by a unit.
                       Allowed units:
                       {s, m, h, d, w} (denoting to seconds, minutes, hours, days, weeks respectively)
            winners - amount of winners on the giveaway
            title - the prize and title of the giveaway
            description - Description of the giveaway, this will be the prize if title is not provided
            holder - Specify a holder for this giveaway, will display the command user as the host if omitted
        """

        # Initialise
        correct_usage = '!start 3d4h ; 1w ; Weapon Slots ; Restrictions: None ; 468631903390400527'
        args = parse.get_args(ctx.message.content, return_length=5)
        giveaway = Giveaway()

        # Validate number of args given
        invalid, valid = [], []
        for arg in args:
            if not arg:
                invalid.append(1)
            else:
                valid.append(arg)
        if len(invalid) > 2:
            raise errors.CustomError(
                "Command requires at least 3 arguments `(duration, winners, title, [description], [holder])`\n"
                f"Found {len(valid)} arguments: `{valid}`\n"
                f"Example usage: `{correct_usage}`"
            )

        duration, winners, title, description, holder = args

        # Define description
        giveaway.description = description.replace('\\n', '\n')

        # Compute and validate duration
        if duration.isdigit():
            duration = int(duration)
        else:
            duration = __to_seconds__(duration)

        giveaway.duration = int(duration + time.time())

        # Find and validate winner amount
        if winners.isdigit():
            giveaway.winners = int(winners)
        else:
            winners_match = re.findall('^(\d*)w', winners)
            if not winners_match:
                raise errors.CustomError(f'Winner amount not found\nCorrect usage: {correct_usage}')
            elif len(winners_match) > 1:
                raise errors.CustomError(
                    f'Multiple winner amounts found: {winners_match}\nCorrect usage: {correct_usage}')
            giveaway.winners = int(winners_match[0])

        # Find holder
        try:
            giveaway.holder = await user_to_holder(ctx=ctx, user_str=holder)
        except errors.NotUser as e:
            return await ctx.reply(embed=e.embed)
        except errors.WarningExtension as e:
            giveaway.holder = e.object
            await ctx.reply(embed=e.embed, delete_after=120)

        # Set prize & description
        giveaway.prize = title
        giveaway.description = description
        # Validate
        if giveaway.prize is not None:  # Can't len(None)
            if len(giveaway.prize) > 256:
                raise errors.CustomError('Giveaway prize (title) length must not be longer than 256\n'
                                         f'```\n{giveaway.prize}```Is {len(giveaway.prize)} characters')

        # Send giveaway
        try:
            giveaway.message = await ctx.channel.send(
                embed=template.running_giveaway(
                    unix=giveaway.duration,
                    winners=giveaway.winners,
                    holder=giveaway.holder,
                    description=giveaway.description,
                    prize=giveaway.prize,
                )
            )
            await giveaway.message.add_reaction('🎉')
        except discord.errors.Forbidden:
            # Determine which permission is missing
            if giveaway.message is not None:
                delete_after = 60
                embed = template.warning(
                    f'I need `Add Reaction` permission at {ctx.channel.mention}.\n'
                    f'Please manually add reaction of 🎉 to [the message]({giveaway.message.jump_url})'
                    f'\n\nThis warning message will be deleted <t:{int(time.time() + delete_after)}:R>'
                )

                await ctx.channel.send(
                    content=ctx.author.mention,
                    embed=embed,
                    delete_after=delete_after
                )
            else:
                raise errors.CustomError(f'I need `Send Messages` permission at {ctx.channel.mention}')

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

        if not giveaway.duration > self.check_end_interval * 60 + time.time():
            asyncio.create_task(self.end_giveaway(document))
        collection.insert(document)
        collection.archive.insert(document)

        try:
            await ctx.message.delete()
        except discord.errors.Forbidden:
            pass

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
            collection.delete(document['_id'])
            return

        server_id, channel_id, message_id = [int(_id) for _id in document['path'].split('/')]
        jump_url = f'https://discord.com/channels/{document["path"]}'
        # Get channel
        try:
            channel = await template.get_channel(self.bot, channel_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException, discord.InvalidData) as error:
            collection.delete(document['_id'])
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
                collection.delete(document['_id'])
                return await channel.send(
                    embed=template.error(
                        'Hmm I can\'t seem to find a giveaway that\'s supposed to end at this time\n'
                        f'Please report to `{str(self.bot.owner)}` if you believe this is the bot\'s fault.\n\n'
                        f'Debug info:\n```json\n{json.dumps(document, indent=4, ensure_ascii=False)}```'
                    )
                )
            # if no perm to send error message, send to owner
            except discord.Forbidden:
                collection.delete(document['_id'])
                return await self.bot.owner.send(
                    f'Forbidden on sending following error\n'
                    f'Giveaway not found\n```{document}```'
                )
        # Catch all other errors on fetching message
        except Exception as error:
            tb = traceback.format_exception(type(error), error, error.__traceback__)
            tb_str = ''.join(tb[:-1]) + f'\n{tb[-1]}'
            collection.delete(document['_id'])
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
            collection.delete(document['_id'])
            return await channel.send(embed=template.no_winner(jump_url, '**Warning:**\nEmbed on giveaway was deleted'))

        # Determine winner
        winners = await draw_winner(message.reactions, self.bot.user, document['winners'])
        if not winners:
            collection.delete(document['_id'])
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
        collection.delete(document['_id'])

    async def wait_and_mention(
            self,
            thread_id: int,
            mentions: Iterable[str],
            winner_id: int,
            ref_message: discord.Message = None
    ) -> None:
        """Waits for winner to send first message and mentions item holder

        :param thread_id: the thread to wait for a reply
        :param mentions: strings of user mentions
        :param winner_id: user id to wait for message
        :param ref_message: the message to refer to
        """

        def check(message):
            if message.channel.id == thread_id:
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
            thread, message = await template.create_ticket(
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
                thread_id=thread.id,
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
            jump_url: str,
            reroll: bool = False
    ):
        """Sends giveaway result and creates ticket if in giveaway channel

        Parameters:
            channel: the channel to send result in
            holder: item holder
            giveaway_title: title of the giveaway message
            giveaway_description: description of the giveaway message
            winners: list of winners
            jump_url: url of original giveaway message
            reroll: True if used for reroll
        """
        create_ticket = True if channel.id in config['giveaway_channels'] else False

        # Send winner notification
        await channel.send(
            **template.giveaway_result(
                winners=[winner.mention for winner in winners],
                giveaway_title=giveaway_title,
                giveaway_description=giveaway_description,
                holder=holder,
                giveaway_link=jump_url,
                mention_users=not create_ticket,
                reroll=reroll
            )
        )

        # Create ticket for winner to contact holder
        if create_ticket:
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

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, event):
        if collection.archive.find(str(event.message_id)) is not None:
            await self.check_disqualified(event)

    async def check_disqualified(self, event: discord.RawReactionActionEvent):
        """checks if a user who entered giveaway has disqualified role, removes reaction if yes"""
        channel = await template.get_channel(self.bot, event.channel_id)
        partial_message = channel.get_partial_message(event.message_id)
        message_link = f'https://discord.com/channels/{event.guild_id}/{event.channel_id}/{event.message_id}'
        if config['disqualified_role_id'] in [role.id for role in event.member.roles]:
            await partial_message.remove_reaction('🎉', event.member)
            embed = discord.Embed(
                title='Reaction removed',
                colour=discord.Colour.red(),
                description=f'Removed reaction from '
                            f'[message]({message_link}) '
                            f'by <@{event.member.id}>'
            )
            await self.bot.log_channel.send(embed=embed)

    async def cog_check(self, ctx):
        if isinstance(ctx.channel, discord.DMChannel):
            return False

        allowed = False
        if ctx.author == ctx.guild.owner:
            allowed = True

        for role in ctx.author.roles:
            if role.permissions.administrator:
                allowed = True
            elif role.id in config['giveaway_role_ids']:
                allowed = True

        if allowed:
            embed = discord.Embed(
                title='Command used',
                description=f'```\n{ctx.message.content}```',
                colour=discord.Colour.blue()
            )
            embed.add_field(
                name="author",
                value=f'{ctx.author.id} | {str(ctx.author)}'
            )
            embed.add_field(
                name='Channel',
                value=f'{str(ctx.channel)}\n{ctx.message.jump_url}',
                inline=False
            )
            await self.bot.log_channel.send(embed=embed)

        return allowed

    async def cog_load(self):
        if config['modmail_channel_id']:
            self.thread_channel = await template.get_channel(self.bot, config['modmail_channel_id'])
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
    :return: (int) seconds
    """
    disallowed = re.findall('[^ 0-9smhdw]', duration.strip())
    if disallowed:
        if len(disallowed) == 1:
            disallowed = disallowed[0]
        raise errors.DisallowedChars(
            f'Disallowed characters found in duration of giveaway: `{disallowed}`\n'
            f'Must have digit(s) followed by s, m, h, d or w'
        )

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
            raise errors.NoPrecedingValue(
                'Unit must be immediately preceded by an integer\n'
                f'Found unit `{unit}` with no preceding integer'
            )
        if unit in matched_units:
            raise errors.DuplicateUnit(
                'Cannot have more than 1 match of same unit in duration of giveaway\n'
                f'Found: `{["".join(re_match) for re_match in matches]}`'
            )
        else:
            matched_units[unit] = None
            seconds += int(num) * TO_SECONDS_MULTIPLIER[unit]

    return seconds


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


async def user_to_holder(ctx: commands.Context, user_str: str) -> template.Holder:
    """
    turns a user string to holder object
    :param ctx: commands.Context
    :param user_str: the user string to do the lookup with
    :return: returns a holder object with attributes populated
    """
    # Initialise
    holder = template.Holder()

    pattern = '|'.join([r'\d{' + str(id_len) + '}' for id_len in range(19, 16, -1)]) + '|$'
    match_ = re.search(pattern, user_str).group()
    id_ = int(match_) if match_ else None
    try:
        member = await template.get_member(ctx=ctx, user_id=id_, user_str=user_str)
        holder.tag = str(member)
        holder.mention = member.mention
        holder.id = member.id
        holder.string = f'Contact {holder.tag} to claim your prize'
        return holder
    except errors.WarningExtension as e:
        # Set holder to author if member not found
        holder.tag = str(ctx.author)
        holder.mention = ctx.author.mention
        holder.id = ctx.author.id
        holder.string = f'Hosted by: {holder.tag}'
        raise errors.WarningExtension(holder, f'{e.message}\nItem holder has been set to command author.')

if __name__ == '__main__':
    pass
