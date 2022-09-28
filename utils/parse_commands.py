import re
import json
from typing import Union

with open('config.json', encoding='utf-8') as file:
    config = json.load(file)


class IncorrectCommandFormat(Exception):
    pass


def get_args(content: str,
             arg_delimiter: str = config['arg_delimiter'],
             prefix: str = config['prefix'],
             return_length: int = None,
             join_excess: bool = False
             ) -> Union[list, str]:
    """Gets argument from message content

    :param content: message content (whole message)
    :param arg_delimiter: delimiter for arguments, if None, all arguments returned in 1 string
    :param prefix: prefix of command
    :param return_length: length of return value will be fixed to this value, ignored if arg_delimiter is None.
    :param join_excess: if True: args after return_length-th arg will be joined together as the last arg. else discards
    :return: arguments
    """
    prefix_match = re.search(f'({prefix})( )?', content)

    if prefix_match is None:
        raise IncorrectCommandFormat(f'Prefix {prefix} not found in content')

    prefix_start, prefix_end = prefix_match.span()
    if prefix_start != 0:
        raise IncorrectCommandFormat(f'Prefix not at position 0 of content, span: {prefix_match.span()}')

    command_end = content[prefix_end:].find(' ')
    args = content[prefix_end+command_end+1:]
    if (command_end == -1) or (args.strip() == ''):
        if return_length:
            return [None for _ in range(return_length)]
        return []

    if not arg_delimiter:
        return args

    output = [arg.strip(' \t') for arg in args.split(arg_delimiter)]
    if return_length:
        if len(output) < return_length:
            output.extend(None for _ in range(return_length-len(output)))
        elif len(output) > return_length:
            if join_excess:
                output = [*output[:return_length-1], ''.join(output[return_length:])]
            else:
                output = output[:return_length]

    return output


if __name__ == '__main__':
    print(get_args('''!start 10s ; 1w ; PC | R3764
Vulkar vexi-critacan ; 
__**Restrictions: **__
Must be MR14+, Must have 700+ kills on Vulkar

Donated By: @Threads#6434
__**Contact @07꞉19#0719 for Pickup**__'''))
