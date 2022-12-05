import utils.template as template

class CustomError(Exception):
    """To be used as superclass for errors to be identified as a custom error"""
    def __init__(self, message='', jump_url=''):
        self.message = message
        self.jump_url = jump_url
        self.__embed = template.error(message, jump_url)

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
        self.__embed = template.error(message, jump_url)

class DuplicateUnit(CustomError):
    """Raised when duplicate unit found in a giveaway's duration argument"""
    pass


class DisallowedChars(CustomError):
    """Raised when disallowed characters found in a giveaway's duration argument"""
    pass


class NoPrecedingValue(CustomError):
    """Raised when no preceding digits are found before a unit in a giveaway's duration argument"""
    pass


class NotUser(CustomError):
    """Raised when the id given does not represent a user"""
    pass
