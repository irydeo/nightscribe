############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Package init
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

from importlib.metadata import version, PackageNotFoundError
try:
    __version__ = version("nightscribe")
except PackageNotFoundError:
    __version__ = "0.0.0"

__app_name__ = "NightScribe"
