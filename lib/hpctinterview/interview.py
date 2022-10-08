# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#


"""Support for running a basic interview process.

The interview configuration uses YAML and is a list of items with each
item being a mapping. Items are of 6 kinds: `branch`, `include`,
`notice`, `question`, `reset`, `setting`, `update`.

Only the `notice` and `question` items are returned. Item provides
access to the item and the setting. The associated setting value is
set via the `Item.set()` to allow for type conversion and checking,
and value validation.

State for the interview process is maintained in the settings
dictionary. The YAML interview configuration does not contain state
information. With the settings data, the interview process can be
started and resumed.

Supported `type` values:

* `bool`: Boolean (`True`|`False`).
* `csv`: Comma-separated value.
* `float`: Float.
* `int`: Integer.
* `ssv`: Whitespace-separated value.

All Items
---------

Fields:

* `kind`: Item kind.
* `name`: Item name.
* `disabled`: Ignore or not: `True`|`False`. Default is `False`.
* `section`: Section name. Provides a namespace for keys and is
    used to provide a fully qualified key:
    `[<section>.]<key>[.<index>]`.
* `key`: Setting name.
* `type`: Type of value.
* `value`: Value to set.

Branch
------

Provides a block of items under an "interview" subtree.

A branch item is a container and does not carry any semantic meaning
or state. It allows for conditional use if a `match_name` and
`match_values` are provided, otherwise the branch is unconditional.

Fields:

* `kind`: `branch`
* `interview:` Subtree of interview items.
* `name`: Item name.
* `match_name`: Setting name to check.
* `match_values`: List of values to select the branch.


Include
-------

Include (by replacing) the item with the contents of a named YAML file.
The contents must be a valid item or list of items. Subtrees are valid.

Fields:

* `kind`: `include`
* `path`: Path of the YAML file.

Notice
------

The `notice` provides information only.

Fields:

* `kind`: `notice`
* `name`: Item name.
* `section`: Section name.
* `text`: Notice text.
* `title`: Title for item.
* `key`: Setting name.
* `type`: Type of value.
* `value`: Setting value.

Question
--------

Presents a question, accepts input, and adds a setting based on the
input.

Fields:

* `kind`: `question`
* `default`: Default value.
* `force`: Force item even if setting exists.
* `key`: Setting name.
* `multivalue`: `True`|`False`.
* `name`: Item name.
* `range`: Range validation: `<lo>-<hi>[:<step>]`.
* `section`: Section name.
* `title`: Title for item.
* `text`: Question text.
* `type`: Type of value.
* `regexp`: Regular expression validation.
* `required`: A value is required: `True`|`False`.
* `value`: Value to set.
* `values`: Values validation.
* `values_from_directory`: Load directory entries into `values`:
    `(dir|file|dir+file):<path>`.
* `values_from_file`: Load lines from file into `values`: `<path>`.
* `values_regexp`: Values regular expression filter.
* `values_sort`: Sort values: `asc`, `desc`.

Warning: `force` should only be used at the end of a conditional
branch. Otherwise it will always be returned by walk.

Reset
-----

Deletes one or more settings and optionally sets a value.

Fields:

* `kind`: `reset`
* `name`: Item name.
* `section`: Section name.
* `reset_keys`: Settings keys to reset/delete.
* `reset_key_regexp`: Setting key regular expression to reset/delete.
* `key`: Setting name.
* `type`: Type of value.
* `value`: Setting value.

Set
---

Shares the same fields as `question` except for those UI-related, and
performs quietly.

Warning: `force` should only be used at the end of a conditional
branch. Otherwise it will always be returned by walk.

Update
------

Update a setting (typically a counter).

Fields:

* `kind`: `update`
* `key`: Settings key.
* `name`: Item name.
* `type`: Value type (expected `int`).
* `value`: Amount to increase setting.
"""


import getpass
import os
import re
import sys
import time
from typing import Any, Union
import yaml

from hpctinterview.lib import DottedDictWrapper


class BadItem(Exception):
    pass


class NoValue:
    pass


class RetryWalk(Exception):
    pass


class Item:
    """Interview item.

    This object is returned by `Interview.next()`. It is the proper means
    of updating settings.
    """

    def __init__(self, interview: "Interview", walkpath: str, key: str, config: dict):
        self.interview = interview
        self.walkpath = walkpath
        self.key = key
        self.config = config
        self.kind = config.get("kind")

        # runtime "default" setting
        if "default_from_file" in config:
            self.config["default"] = open(config["default_from_file"]).read()

        # runtime "values" settings
        if "values_from_directory" in config:
            namekind, path = config["values_from_directory"].split(":", 1)
            for _, dirnames, filenames in os.walk(path):
                break

            if namekind == "dir":
                names = dirnames
            elif namekind == "file":
                names = filenames
            elif namekind == "dir+file":
                names = dirnames + filenames

            config["values"] = names

        if "values_from_file" in config:
            path = config["values_from_file"]
            config["values"] = [v for v in open(path).read().split("\n") if v != ""]

        # filter values
        if "values_regexp" in config:
            cre = re.compile(config["values_regexp"])
            if "values" in config:
                config["values"] = [v for v in config["values"] if cre.match(v)]

        # process values
        if "values" in config:
            # convert values
            if config["type"] in ["int", "float"]:
                if config["type"] == "int":
                    cls = int
                elif config["type"] == "float":
                    cls = float
                config["values"] = [cls(v) for v in config["values"]]

            # sort values
            if "values_sort" in config:
                order = config["values_sort"]
                if order == "asc":
                    config["values"] = sorted(config["values"])
                elif order == "desc":
                    config["values"] = reverse(config["values"])

    def get(self, key, default=None) -> dict:
        """Return interview item configuration."""

        return self.config.get(key, default)

    def get_fqkey(self, key=None):
        """Get fully qualified key.

        A fully qualified key is: `[<section>.]<key>[.<count>]`
        where `<section>` is `section` from the item configuration
        and `<count>` comes from the key in the `paramterize` item
        configuration.

        Parameterization allows for collecting information from
        loops in the interview process.

        Args:
            item_config: Item configuration.
            key: Alternate key setting.
        """

        section = self.config.get("section", NoValue)
        if key == None:
            key = self.config.get("key")

        if "." not in key:
            if section != NoValue:
                key = f"{section}.{key}"

        # parameterize key
        parameterize = self.config.get("parameterize", NoValue)
        if parameterize != NoValue:
            counter_key = self.config["parameterize"]
            count = int(self.interview.settings.get(counter_key, 0))
            key = f"{key}.{count}"

        return key

    def set(self, value) -> None:
        """Set settings value.

        value is converted to the proper type. Validation is performed
        if `values` is provided.
        """

        key = self.key
        typ = self.config["type"]

        # ignore/reset value for special case
        if self.kind in ["notice"]:
            if "default" not in self.config:
                raise BadItem("notice requires a default")
            value = None

        # get default
        if "default" in self.config:
            if value in [None, ""]:
                value = self.config["default"]

        try:
            # convert value
            if typ == "bool":
                value = bool(value)
            elif typ == "csv":
                value = value.split(",")
            if typ == "float":
                value = float(value)
            elif typ == "int":
                value = int(value)
            elif typ == "str":
                pass
            elif typ == "ssv":
                value = value.split()

            # aliases
            multivalue = bool(self.config.get("multivalue", False))
            regexp = self.config.get("regexp", NoValue)
            required = bool(self.config.get("required", False))
            rng = self.config.get("range", NoValue)
            values = self.config.get("values", NoValue)

            # listify value if needed for easier validation later
            if type(value) == list:
                if not multivalue:
                    raise ValueError("bad value")
                xvalues = value
            else:
                xvalues = [value]

            # validate value
            if required and not xvalues:
                raise ValueError("required value")

            elif values != NoValue:
                for v in xvalues:
                    if v not in values:
                        raise ValueError("bad value")

            elif regexp != NoValue:
                cre = re.compile(regexp)
                for v in xvalues:
                    if not cre.match(v):
                        raise ValueError("bad value")

            elif rng != NoValue:
                # split range into lo, hi, step
                lo, hi = rng.split("-", 1)

                if ":" in hi:
                    hi, step = hi.split(":", 1)
                else:
                    step = 1

                if typ == "int":
                    lo = int(lo)
                    hi = int(hi)
                    step = int(step) if step != "" else 1
                elif typ == "float":
                    lo = float(lo)
                    hi = float(hi)
                    step = float(step) if step != "" else 1.0

                # check values
                for v in xvalues:
                    if v < lo or v > hi or (v - lo) % step != 0:
                        raise ValueError("bad value")

            # update interview settings
            self.interview.settings[key] = value
        except Exception as e:
            raise


class Branch(Item):
    pass


class Include(Item):
    pass


class Notice(Item):
    pass


class Question(Item):
    pass


class Reset(Item):
    pass


class Set(Item):
    pass


class Update(Item):
    pass


item_cls_lookup = {
    "branch": Branch,
    "include": Include,
    "notice": Notice,
    "question": Question,
    "reset": Reset,
    "set": Set,
    "update": Update,
}


class Interview:
    """Class to select next interview item to process based on a YAML
    description.
    """

    def __init__(
        self,
        home=None,
        config: Union[dict, None] = None,
        settings: Union[dict, None] = None,
    ):
        self.home = home
        self.config = config or {}
        self._settings = settings or {}
        self.settings = DottedDictWrapper(self._settings)

    def _load(self, path):
        """Load YAML configuration and return."""

        if "/" not in path and self.home != None:
            path = f"{self.home}/{path}"
        return yaml.safe_load(open(path, "r"))

    def load(self, path):
        """Load YAML configuration."""

        self.config = self._load(path)

    def next(self) -> Union[Item, None]:
        """Find and return the"""

        def get_fqkey(item_config, key=None):
            """Get fully qualified key.

            A fully qualified key is: `[<section>.]<key>[.<count>]`
            where `<section>` is `section` from the item configuration
            and `<count>` comes from the key in the `paramterize` item
            configuration.

            Parameterization allows for collecting information from
            loops in the interview process.

            Args:
                item_config: Item configuration.
                key: Alternate key setting.
            """

            section = item_config.get("section", NoValue)
            if key == None:
                key = item_config.get("key")

            # print(f"""*** {item_config}""")
            # print(f"""*** {item_config.get("kind")} {key}""")
            if "." not in key:
                if section != NoValue:
                    key = f"{section}.{key}"

            # parameterize key
            parameterize = item_config.get("parameterize", NoValue)
            if parameterize != NoValue:
                counter_key = item_config["parameterize"]
                count = int(self.settings.get(counter_key, 0))
                key = f"{key}.{count}"

            return key

        def walk(config, walkpath):
            """Walk the interview tree and find the next item based on
            the `settings` state.
            """

            # print(f"walk() walkpath ({walkpath}) config ({config})")
            for i, item_config in enumerate(config):
                disabled = bool(item_config.get("disabled", False))

                if disabled:
                    continue

                # aliases
                key = item_config.get("key", NoValue)
                kind = item_config.get("kind", NoValue)
                item_cls = item_cls_lookup.get(kind)
                if item_cls == None:
                    raise Exception("unknown kind")
                item = item_cls(self, walkpath, key, item_config)

                # print(f"""kind ({kind})""")

                # find item
                if kind in ["branch", "notice", "question", "set", "reset"]:
                    # all these kinds "set" values if available

                    if kind == "branch":
                        # special case for "branch"
                        match_key = item.get("match_key", NoValue)
                        match_values = item.get("match_values", NoValue)
                        match_not_values = item.get("match_not_values", NoValue)

                        if match_key != NoValue:
                            match_key = item.get_fqkey(match_key)
                            match_value = settings.get(match_key, NoValue)

                            if (match_values == NoValue or match_value not in match_values) and (
                                match_not_values == NoValue or match_value in match_not_values
                            ):
                                # no match, fallback to next or parent
                                continue

                        # match, continue below

                    elif kind == "reset":
                        # special case for "reset"
                        reset_keys = item.get("reset_keys", NoValue)
                        reset_key_regexp = item.get("reset_key_regexp", NoValue)

                        if reset_keys != NoValue:
                            for reset_key in reset_keys:
                                reset_key = item.get_fqkey(reset_key)
                                if reset_key in settings:
                                    del settings[reset_key]

                        elif reset_key_regexp != NoValue:
                            cre = re.compile(reset_key_regexp)
                            for key in list(settings.keys()):
                                if cre.match(key):
                                    del settings[key]
                        else:
                            raise ValueError("bad item")

                    # set value as/if needed
                    if "key" in item_config:
                        key = item.get_fqkey()
                        curr_value = settings.get(key, NoValue)
                        force = bool(item.get("force", False))

                        if curr_value == NoValue or force:
                            if kind in ["branch", "reset", "set"]:
                                value = item.get("value")
                                item.set(value)

                                if kind in ["reset", "set"]:
                                    raise RetryWalk()

                            elif kind in ["notice", "question"]:
                                return item

                    # handle branch match now
                    if kind == "branch":
                        interview = item.get("interview", NoValue)
                        if interview:
                            item = walk(interview, walkpath + [i])
                            if item != None:
                                return item
                            else:
                                continue

                elif kind == "include":
                    # replace with branch and included content
                    path = item.get("path", NoValue)
                    # print(f"include ({kind}) ({path})")

                    if path != NoValue:
                        # TODO: change to Include.reload/reconfig?
                        item_config.clear()
                        item_config["kind"] = "branch"
                        item_config["name"] = f"included-{path}"
                        item_config["interview"] = self._load(path)
                        # print(f"""************* {self.config}""")
                        raise RetryWalk()

                elif kind == "reset":
                    reset_keys = item.get("reset_keys", NoValue)
                    reset_key_regexp = item.get("reset_key_regexp", NoValue)

                    if reset_keys != NoValue:
                        for reset_key in reset_keys:
                            reset_key = item.get_fqkey(reset_key)
                            if reset_key in settings:
                                del settings[reset_key]

                    elif reset_key_regexp != NoValue:
                        cre = re.compile(reset_key_regexp)
                        for key in list(settings.keys()):
                            if cre.match(key):
                                del settings[key]
                    else:
                        raise ValueError("bad item")

                    # update value, if present
                    key = item.get("key", NoValue)
                    if key != NoValue:
                        key = item.get_fqkey()
                        value = item.get("value")
                        item.set(value)

                    raise RetryWalk()

                elif kind == "update":
                    key = item.get("key")
                    value = int(item.get("value", 1))
                    count = int(settings.get(key, 0))
                    item.set(count + value)

                else:
                    # should not get here
                    # print(f" ** {item_config}")
                    raise Exception("invalid item")

            return None

        config = self.config
        settings = self.settings

        # find item
        # `RetryWalk` calls for another walk
        while True:
            try:
                return walk(config, [])
            except RetryWalk:
                continue

    def check(self):
        """Check the items tree to ensure that they are valid with
        respect to various aspects.
        """

        def walk(config, walkpath=None):

            for i, item_config in enumerate(config):
                kind = item_config.get("kind", NoValue)

                if kind == NoValue:
                    raise BadItem(f"kind missing from item ({item_config}) at ({walkpath})")

                # do not move!
                # replace include *before* branch!
                if kind == "include":
                    # replace with branch and included content
                    path = item_config.get("path", NoValue)

                    if path == NoValue:
                        raise BadItem(
                            f"path missing for include item ({item_config}) at ({walkpath})"
                        )

                    if not os.path.exists(path):
                        raise BadItem(
                            f"file not found for include item ({item_config} at ({walkpath})"
                        )

                    if path != NoValue:
                        item_config.clear()
                        item_config["kind"] = "branch"
                        item_config["name"] = f"included-{path}"
                        item_config["interview"] = self._load(path)

                if kind == "branch":
                    walk(item_config, walkpath + [i])

                elif kind in ["question", "set"]:
                    for k in ["key", "title", "text"]:
                        if k not in item_config:
                            raise BadItem(
                                f"{k} missing for question/set item ({item_config}) at ({walkpath})"
                            )

    def test(self, answers=None, expected=None, verbose=False) -> None:
        """Test the interview in the terminal.

        Args:
            answers: A text file containing prepared answers to the
                interview questions. Each line must be:
                "answer: <answer>". If not provided, the test is done
                at the prompt.
            expected: A dictionary containing expected settings based
                on the interview and answers.
        """

        while True:
            item = self.next()

            if item == None:
                break

            if verbose:
                print(
                    "==========\n"
                    f"""walkpath:           {item.walkpath}\n"""
                    f"""name:               {item.get("name", "-")}\n"""
                    f"""section:            {item.get("section", "-")}\n"""
                    f"""key:                {item.get("key", "-")}\n"""
                    f"""fqkey:              {item.key}\n"""
                    f"""parameterize:       {item.get("parameterize", "-")}\n"""
                    f"""type:               {item.get("type", "-")}\n"""
                    f"""hidden:             {item.get("hidden", "-")}\n"""
                    f"""multivalue:         {item.get("multivalue", "-")}\n"""
                    f"""range:              {item.get("range", "-")}\n"""
                    f"""regexp:             {item.get("regexp", "-")}\n"""
                    f"""required:           {item.get("required", "-")}\n"""
                    "----------\n"
                )

            print(
                f"""title:              {item.get("title", "-")}\n"""
                f"""text:               {item.get("text", "-")}\n"""
                f"""values:             {item.get("values", "-")}\n"""
                f"""default:            {item.get("default", "-")}"""
            )

            try:
                try:
                    if answers != None:
                        ctxt = []
                        while answers:
                            line = answers.pop(0)
                            if line.startswith("answer:"):
                                reply = line[7:]
                                reply = reply.strip()
                                break
                            else:
                                if not line.startswith("====="):
                                    ctxt.append(line)

                            if 0 and verbose:
                                print(f"context: {ctxt}")

                        else:
                            raise Exception("not enough answers for interview")

                        if verbose:
                            print(f"answer: {reply}")
                    else:
                        if bool(item.get("hidden", False)):
                            reply = getpass.getpass("answer: ")
                        else:
                            default = item.get("default", "")
                            reply = input(f"answer [{default}]: ")

                    item.set(reply)
                except KeyboardInterrupt:
                    input("\nCTRL-C to exit, ENTER to print settings")
                    print(self.settings)

            except KeyboardInterrupt:
                print("\nexiting prematurely")
                return
            except Exception as e:
                import traceback

                traceback.print_exc()
                print(f"error ({e})")
                sys.exit(1)

        print("==========")

        if answers != None and answers:
            print("there are unused answers")

    def compare_results(self, expected):
        """Compare expected results with settings."""

        results = self.settings

        ekeys = expected.keys()
        rkeys = results.keys()

        # shared_keys = set(ekeys).intersection(rkeys)
        # only_ekeys = set(ekeys).difference(rkeys)
        # only_rkeys = set(rkeys).difference(ekeys)
        all_keys = set(ekeys).union(rkeys)

        # print(f"shared keys:         {shared_keys}")
        # print(f"expected keys only:  {only_ekeys}")
        # print(f"settings keys only:  {only_rkeys}")
        # print("----------")

        for key in sorted(all_keys):
            evalue = expected.get(key, NoValue)
            rvalue = self.settings.get(key, NoValue)

            print(f"key:      {key}")
            print(f"result:   {rvalue}")
            print(f"expected: {evalue}")
            if evalue != rvalue:
                print("  *** mismatch ***")
            print("----------")
