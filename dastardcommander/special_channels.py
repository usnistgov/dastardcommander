import json
import os


class SpecialChannels:
    """
    Handle a more-or-less permanent list of channels that are considered "special" and should be
    remembered. For instance, a list of channels that should be blocked from triggering no matter
    what the user asks for. That is, any "all channels" settings
    will not allow triggering of these channels.

    Values are stored to and read from a config file (default: ~/.dastard/{configName}.json),
    including a history of the last several lists.

    Usage:
    >>> import tempfile
    >>> backingfile = tempfile.mkstemp(suffix=".json")[1]
    >>> tb = SpecialChannels(backingfile)
    >>> print(tb.special)
    []
    >>> tb.add_chan_to_list(6,4,2)
    True
    >>> print(tb.special)
    [2, 4, 6]
    >>> tb.add_chan_to_list(8,6,[4,2],4,6,8)
    True
    >>> print(tb.special)
    [2, 4, 6, 8]
    >>> tb.toggle_channel(3)
    True
    >>> print(tb.special)
    [2, 3, 4, 6, 8]
    >>> tb.toggle_channel(3)
    True
    >>> print(tb.special)
    [2, 4, 6, 8]
    >>> tb.remove_chan_from_list(4)
    True
    >>> print(tb.special)
    [2, 6, 8]
    >>> tb.remove_chan_from_list(4)
    False
    >>> tb.revert_prev()
    >>> print(tb.special)
    [2, 4, 6, 8]
    >>> tb.clear()
    True
    >>> print(tb.special)
    []
    >>> tb.add_chan_to_list(6,4,2)
    True
    >>> tb2 = SpecialChannels(backingfile)
    >>> print(tb2.special)
    [2, 4, 6]
    """

    FIELDS_TO_MEMO = ("special", "special_history")
    HISTORY_LENGTH = 10

    def __init__(self, configfile=None, configName=None):
        if configfile is None:
            assert configName is not None
            configfile = f"~/.dastard/{configName}.json"
        self.config = os.path.expanduser(configfile)
        self.special = []
        self.special_history = []
        self.read_config()

    def read_config(self):
        try:
            with open(self.config, "r", encoding="ascii") as fp:
                data = json.load(fp)
            for field in data:
                if field in self.FIELDS_TO_MEMO:
                    self.__dict__[field] = data[field]
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def write_config(self):
        with open(self.config, "w", encoding="ascii") as fp:
            obj = {field: self.__dict__[field] for field in self.FIELDS_TO_MEMO}
            json.dump(obj, fp)
            fp.write("\n")  # ensure \n at EOF

    def add_chan_to_list(self, *args):
        """Add 1 or more `channels` to the special channels.
        Each chan can be an int or an iterable of them."""
        # Convert a mix of int and list-of-int args to a single list
        channels = []
        for a in args:
            if isinstance(a, list):
                channels.extend(a)
            else:
                channels.append(a)
        any_changed = self._change_channels(channels, special=True)
        return any_changed

    def remove_chan_from_list(self, *args):
        """Remove 1 or more `channels` from the special channels.
        Each chan can be an int or an iterable of them."""
        # Convert a mix of int and list-of-int args to a single list
        channels = []
        for a in args:
            if isinstance(a, list):
                channels.extend(a)
            else:
                channels.append(a)
        any_changed = self._change_channels(channels, special=False)
        return any_changed

    def toggle_channel(self, channel):
        """Add channel to the special list, or remove it, as appropriate."""
        tospecial = channel not in self.special
        return self._change_channels(channel, tospecial)

    def _change_channels(self, channels, special=True):
        if isinstance(channels, int):
            channels = [channels]

        # Use python sets to simplify the logic.
        specialch = set(self.special)
        arguments = set(channels)
        if special:
            specialch.update(arguments)
        else:
            specialch -= arguments

        # Then convert back to a sorted list of channels and notify any connected Qt slots
        any_changed = not (specialch == set(self.special))
        if any_changed:
            self.save_history()
            self.special = list(specialch)
            self.special.sort()
        self.write_config()
        return any_changed

    def revert_prev(self):
        try:
            self.special = self.special_history.pop()
        except IndexError:
            self.special = []
        self.write_config()

    def save_history(self):
        self.special_history.append(self.special)
        if len(self.special_history) >= self.HISTORY_LENGTH:
            self.special_history = self.special_history[-self.HISTORY_LENGTH:]

    def clear(self):
        if len(self.special) == 0:
            return False
        self.save_history()
        self.special = []
        self.write_config()
        return True


if __name__ == "__main__":
    import doctest
    doctest.testmod()
