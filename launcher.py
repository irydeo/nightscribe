############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Standalone launcher (PyInstaller entry point)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import sys

# Absolute-import entry point for the frozen app: PyInstaller runs this as a
# plain script, so we jump into the package CLI from here.

from nightscribe.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
