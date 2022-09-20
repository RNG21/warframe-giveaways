class DuplicateUnit(Exception):
    """Raised when duplicate unit found in a giveaway's duration argument"""
    pass


class DisallowedChars(Exception):
    """Raised when disallowed characters found in a giveaway's duration argument"""
    pass


class NoPrecedingValue(Exception):
    """Raised when no preceding digits are found before a unit in a giveaway's duration argument"""
    pass


class NotUser(Exception):
    """Raised when the id given does not represent a user"""
    pass
