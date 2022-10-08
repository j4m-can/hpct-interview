#! /usr/bin/env python3
#
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# tests/settings_test/settings_test.py

import pprint
import sys

sys.path.insert(0, "../../lib")

from hpctinterview.settings import Settings


def show(filename):
    s = open(filename).read()
    print(f"filename: {filename}")
    print("content")
    print("----------")
    print(s)
    print("----------")

    settings = Settings()
    settings.load("etc.yaml")
    print()
    print("loaded:")
    print("----------")
    pprint.pprint(settings.data, indent=2)
    print("----------")

    print()
    print("items:")
    for k, v in settings.items():
        print(f"{k}: {v}")

    settings.dump(f"dumped-{filename}")


if __name__ == "__main__":
    show("etc.yaml")
