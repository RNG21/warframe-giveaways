import re
import json

with open('config.json', encoding='utf-8') as file:
    config = json.load(file)


class IncorrectCommandFormat(Exception):
    pass


def get_args(content: str, arg_delimiter: str = config['arg_delimiter'], prefix: str = config['prefix']):
    """Gets argument from message content

    :param content: message content (whole message)
    :param arg_delimiter: delimiter for arguments, if None, all arguments returned in a string
    :param prefix: prefix of command
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
        return []

    if not arg_delimiter:
        return args
    return [arg.strip(' \t') for arg in args.split(arg_delimiter)]


if __name__ == '__main__':
    print(get_args('''!start 10s ; 1w ; PC | R3764
Vulkar vexi-critacan ; 
__**Restrictions: **__
Must be MR14+, Must have 700+ kills on Vulkar

Donated By: @Threads#6434
__**Contact @07꞉19#0719 for Pickup**__'''))
