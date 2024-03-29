import re
import json
from typing import Union, List

from discord.ext import commands

from utils import errors

if __name__ == '__main__':
    import os.path
    with open(os.path.dirname(__file__) + '/../config.json', encoding='utf-8') as file:
        config = json.load(file)
else:
    with open('config.json', encoding='utf-8') as file:
        config = json.load(file)


class IncorrectCommandFormat(Exception):
    pass


def get_args(content: str,
             arg_delimiter: str = config['arg_delimiter'],
             prefixes: List[str] = config['prefix'],
             return_length: int = None,
             required: int = 0,
             join_excess: bool = False,
             error_msg: str = ''
             ) -> Union[list, str]:
    """Gets argument from message content

    :param content: message content (whole message)
    :param arg_delimiter: delimiter for arguments, if None, all arguments returned in 1 string
    :param prefixes: prefix of command
    :param return_length: length of return value will be fixed to this value, ignored if arg_delimiter is None.
    :param required: amount of required arguments
    :param join_excess: if True: args after return_length-th arg will be joined together as the last arg. else discards
    :param error_msg: the error message should an error be thrown
    :return: arguments
    """
    prefix_match = re.search(f'({"|".join(prefix for prefix in prefixes)})( )?', content)

    if prefix_match is None:
        raise IncorrectCommandFormat(f'Prefix `{prefixes}` not found in content')

    prefix_start, prefix_end = prefix_match.span()
    if prefix_start != 0:
        raise IncorrectCommandFormat(f'Prefix not at position 0 of content, span: {prefix_match.span()}')

    command_end = content[prefix_end:].find(' ')
    args = content[prefix_end+command_end+1:]
    if (command_end == -1) or (args.strip() == ''):  # No arguments
        if required:
            if error_msg == '':
                error_msg = f'{required} arguments required, 0 provided'
            raise errors.MissingArgument(error_msg)
        if return_length:
            return ['' for _ in range(return_length)]
        return []

    if not arg_delimiter:
        return args

    output = [arg.strip(' \t') for arg in args.split(arg_delimiter)]
    if len(output) < required:
        if error_msg == '':
            error_msg = f'{required} arguments required.\n' \
                        f'{len(output)} provided: `{output}`'
        raise errors.MissingArgument(error_msg)
    if return_length:
        if len(output) < return_length:
            output.extend('' for _ in range(return_length-len(output)))
        elif len(output) > return_length:
            if join_excess:
                output = [*output[:return_length-1], ''.join(output[return_length:])]
            else:
                output = output[:return_length]

    return output


if __name__ == "__main__":
    print(get_args('''g-start 10s ; 1w ; PC | R3764
Vulkar vexi-critacan ; 
__**Restrictions: **__
Must be MR14+, Must have 700+ kills on Vulkar

Donated By: @Threads#6434
__**Contact @07꞉19#0719 for Pickup**__'''))
