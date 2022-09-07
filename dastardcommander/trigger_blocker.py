import json
import os


class TriggerBlocker:
    """
    Handle a more-or-less permanent list of channels that are considered "bad" and should be
    blocked from triggering no matter what the user asks for. That is, any "all channels" settings
    will not allow triggering of these channels.

    Values are stored to and read from a config file (default: ~/.dastard/blocked_channels.json),
    including a history of the last several lists.

    Usage:
    >>> tb = TriggerBlocker(tempfile.mkstemp(suffix=".json")[1])
    >>> tb.block_channels(6,4,2)
    >>> print(tb.blocked)
    [2, 4, 6]
    >>> tb.block_channels(8,6,[4,2],4,6,8)
    >>> print(tb.blocked)
    [2, 4, 6, 8]
    >>> tb.unblock_channels(4)
    >>> print(tb.blocked)
    [2, 6, 8]
    >>> tb.revert_prev()
    >>> print(tb.blocked)
    [2, 4, 6, 8]
    >>> tb.clear()
    >>> print(tb.blocked)
    []
    """

    FIELDS_TO_MEMO = ("blocked", "blocked_history")
    HISTORY_LENGTH = 10

    def __init__(self, configfile=None):
        if configfile is None:
            configfile = "~/.dastard/blocked_channels.json"
        self.config = os.path.expanduser(configfile)
        self.blocked = []
        self.blocked_history = []
        self.read_config()

    def read_config(self):
        try:
            with open(self.config, "r") as fp:
                data = json.load(fp)
                for field in self.FIELDS_TO_MEMO:
                    self.__dict__[field] = data.get(field, [])
        except (FileNotFoundError, json.JSONDecodeError):
            self.blocked = []

    def write_config(self):
        with open(self.config, "w") as fp:
            obj = {field: self.__dict__[field] for field in self.FIELDS_TO_MEMO}
            json.dump(obj, fp)

    def block_channels(self, *channels):
        """Add 1 or more `channels` to the blocked channels. Each chan be an int or an iterable of them."""
        for ch in channels:
            self._change_channels(ch, True)
        self.write_config()

    def unblock_channels(self, *channels):
        """Remove 1 or more `channels` from the blocked channels. Each chan be an int or an iterable of them."""
        for ch in channels:
            self._change_channels(ch, False)
        self.write_config()

    def _change_channels(self, channels, add=True):
        if not isinstance(channels, int) and (channels is None or len(channels) == 0):
            return

        self.save_history()

        if isinstance(channels, int):
            channels = [channels]
        oldch = set(self.blocked)
        newch = set(channels)
        if add:
            oldch.update(newch)
        else:
            oldch -= newch
        self.blocked = list(oldch)
        self.blocked.sort()

    def revert_prev(self):
        try:
            self.blocked = self.blocked_history.pop()
        except IndexError:
            self.blocked = []
        self.write_config()

    def save_history(self):
        self.blocked_history.append(self.blocked)
        if len(self.blocked_history) >= self.HISTORY_LENGTH:
            self.blocked_history = self.blocked_history[-self.HISTORY_LENGTH:]

    def clear(self):
        self.save_history()
        self.blocked = []
        self.write_config()


if __name__ == "__main__":
    import doctest
    import tempfile

    doctest.testmod()
