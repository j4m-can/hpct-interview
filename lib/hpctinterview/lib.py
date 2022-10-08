# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#

import subprocess


class DottedDictWrapper:
    """Wrap an existing dictionary to provide dotted notation
    for keys.

    See https://gist.github.com/j4m-can/d843ed08b0e29125cacb2d5ea349b46a.
    """

    def __init__(self, d=None, sep="."):
        self.d = d if d != None else {}
        self.sep = sep

    def __contains__(self, key):
        try:
            v = self._find(key.split(self.sep))
        except:
            return False
        return True

    def __getitem__(self, key):
        try:
            v = self._find(key.split(self.sep))
            if isinstance(v, dict):
                v = DottedDictWrapper(v, self.sep)
        except:
            raise KeyError(key)
        return v

    def __repr__(self):
        return str(dict(self.items()))

    def __setitem__(self, key, value):
        keys = key.split(self.sep)
        try:
            v = self.d
            for k in keys[:-1]:
                if k not in v:
                    v[k] = {}
                    v = v[k]
                elif isinstance(v, dict):
                    v = v[k]
                else:
                    # already set
                    raise Exception()
            v[keys[-1]] = value
        except:
            raise KeyError(key)

    def _find(self, keys):
        v = self.d
        for k in keys:
            if isinstance(v, dict):
                v = v[k]
            else:
                raise KeyError(self.sep.join(keys))
        return v

    def _walk(self, d, pref=None):
        for k in d:
            _pref = f"{pref}{self.sep}{k}" if pref else k
            v = d[k]
            if isinstance(v, dict):
                yield from self._walk(v, _pref)
            else:
                yield (_pref, v)

    def copy(self):
        return self.__class__(self.d.copy(), self.sep)

    def get(self, key, default=None):
        if key in self:
            return self[key]
        return default

    def keys(self):
        for k, _ in self._walk(self.d):
            yield k

    def items(self):
        for k, v in self._walk(self.d):
            yield (k, v)

    def update(self, d):
        self.d.update(d)

    def values(self):
        for _, v in self._walk(self.d):
            yield v


def run(args, stdin=None):
    """Execute command and return full capture of stderr, stdout with
    wait.
    """

    result = subprocess.run(args, stdin=stdin, capture_output=True, text=True)
    return result


def bash_run(args, stdin=None):
    """Execute command in bash and return full capture of stderr,
    stdout with wait.
    """

    result = subprocess.run(args, stdin=stdin, shell="/bin/bash", capture_output=True, text=True)
    return result
