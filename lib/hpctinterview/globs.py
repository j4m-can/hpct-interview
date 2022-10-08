# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# lib/hpct-interview/globs.py


import os.path as __ospath
import sys as __sys

APP_EXEC = __ospath.realpath(__sys.argv[0])
APP_NAME = __ospath.basename(APP_EXEC)
BIN_DIR = __ospath.dirname(APP_EXEC)
APP_DIR = __ospath.dirname(BIN_DIR)

ETC_DIR = f"{APP_DIR}/etc/hpct-interview"
LIB_DIR = f"{APP_DIR}/lib/hpct-interview"
