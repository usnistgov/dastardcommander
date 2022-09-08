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
    >>> backingfile = tempfile.mkstemp(suffix=".json")[1]
    >>> tb = TriggerBlocker(backingfile)
    >>> print(tb.blocked)
    []
    >>> tb.block_channels(6,4,2)
    True
    >>> print(tb.blocked)
    [2, 4, 6]
    >>> tb.block_channels(8,6,[4,2],4,6,8)
    True
    >>> print(tb.blocked)
    [2, 4, 6, 8]
    >>> tb.toggle_channel(3)
    True
    >>> print(tb.blocked)
    [2, 3, 4, 6, 8]
    >>> tb.toggle_channel(3)
    True
    >>> print(tb.blocked)
    [2, 4, 6, 8]
    >>> tb.unblock_channels(4)
    True
    >>> print(tb.blocked)
    [2, 6, 8]
    >>> tb.unblock_channels(4)
    False
    >>> tb.revert_prev()
    >>> print(tb.blocked)
    [2, 4, 6, 8]
    >>> tb.clear()
    True
    >>> print(tb.blocked)
    []
    >>> tb.block_channels(6,4,2)
    True
    >>> tb2 = TriggerBlocker(backingfile)
    >>> print(tb2.blocked)
    [2, 4, 6]
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
            for field in data:
                if field in self.FIELDS_TO_MEMO:
                    self.__dict__[field] = data[field]
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def write_config(self):
        with open(self.config, "w") as fp:
            obj = {field: self.__dict__[field] for field in self.FIELDS_TO_MEMO}
            json.dump(obj, fp)
            fp.write("\n")  # ensure \n at EOF

    def block_channels(self, *args):
        """Add 1 or more `channels` to the blocked channels. Each chan be an int or an iterable of them."""
        # Convert a mix of int and list-of-int args to a single list
        channels = []
        for a in args:
            if isinstance(a, list):
                channels.extend(a)
            else:
                channels.append(a)
        any_changed = self._change_channels(channels, block=True)
        return any_changed

    def unblock_channels(self, *args):
        """Remove 1 or more `channels` from the blocked channels. Each chan be an int or an iterable of them."""
        # Convert a mix of int and list-of-int args to a single list
        channels = []
        for a in args:
            if isinstance(a, list):
                channels.extend(a)
            else:
                channels.append(a)
        any_changed = self._change_channels(channels, block=False)
        return any_changed

    def toggle_channel(self, channel):
        """Add channel to the block list, or remove it, as appropriate."""
        toblock = channel not in self.blocked
        return self._change_channels(channel, toblock)

    def _change_channels(self, channels, block=True):
        if isinstance(channels, int):
            channels = [channels]

        # Use python sets to simplify the logic.
        blockedch = set(self.blocked)
        arguments = set(channels)
        if block:
            blockedch.update(arguments)
        else:
            blockedch -= arguments

        # Then convert back to a sorted list of channels and notify any connected Qt slots
        any_changed = not (blockedch == set(self.blocked))
        if any_changed:
            self.save_history()
            self.blocked = list(blockedch)
            self.blocked.sort()
        self.write_config()
        return any_changed

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
        if len(self.blocked) == 0:
            return False
        self.save_history()
        self.blocked = []
        self.write_config()
        return True


if __name__ == "__main__":
    import doctest
    import tempfile

    doctest.testmod()
