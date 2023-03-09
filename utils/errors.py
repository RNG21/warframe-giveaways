from typing import Union, Literal

import utils.template as template


class CustomError(Exception):
    """To be used as superclass for errors to be identified as a custom error"""

    def __init__(self, message='', jump_url='', *, type_: Literal['error', 'warning'] = 'error'):
        if type_ not in ['error', 'warning']:
            raise Exception("type_ not in ['error', 'warning']")
        self.type = type_
        self.message = message
        self.jump_url = jump_url
        if self.type == 'error':
            self.__embed = template.error(message, jump_url)
        else:
            self.__embed = template.warning(message)

    def __str__(self):
        return self.message

    @property
    def embed(self):
        if not self.__embed.description:
            print(f'[{type(self).__name__}] embed description is empty')
        return self.__embed

    @embed.setter
    def embed(self, args):
        try:
            message, jump_url = args
        except ValueError:
            raise CustomError()
        if self.type == 'error':
            self.__embed = template.error(message, jump_url)
        else:
            self.__embed = template.warning(message)


class DuplicateUnit(CustomError):
    """Raised when duplicate unit found in a giveaway's duration argument"""


class DisallowedChars(CustomError):
    """Raised when disallowed characters found in a giveaway's duration argument"""


class NoPrecedingValue(CustomError):
    """Raised when no preceding digits are found before a unit in a giveaway's duration argument"""


class NotUser(CustomError):
    """Raised when the id given does not represent a user"""


class MissingArgument(Exception):
    """Raised when insufficient arguments were provided **internally within the program**"""


class WarningExtension(CustomError):
    """Warning extended with an attribute to pass on values"""
    def __init__(self, object_, *args):
        self.object = object_
        super().__init__(*args, type_='warning')
