#!/usr/bin/python
# -*- coding:Utf-8 -*-
#
#  Copyright (C) 2010 Mathieu Comandon <strider@strycore.com>
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License version 3 as
#  published by the Free Software Foundation.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
"""Handle the basic configuration of Lutris."""

import os
import sys
import yaml
import logging
from os.path import join

from gi.repository import Gio

from lutris import pga
from lutris.util.log import logger
from lutris import settings


def register_handler():
    """ Register the lutris: protocol to open with the application. """
    logger.debug("registering protocol")
    executable = os.path.abspath(sys.argv[0])
    base_key = "desktop.gnome.url-handlers.lutris"
    schema_directory = "/usr/share/glib-2.0/schemas/"
    schema_source = Gio.SettingsSchemaSource.new_from_directory(
        schema_directory, None, True
    )
    schema = schema_source.lookup(base_key, True)
    if schema:
        settings = Gio.Settings.new(base_key)
        settings.set_string('command', executable)
    else:
        logger.warning("Schema not installed, cannot register url-handler")


def check_config(force_wipe=False):
    """Check if initial configuration is correct."""
    directories = [settings.CONFIG_DIR,
                   join(settings.CONFIG_DIR, "runners"),
                   join(settings.CONFIG_DIR, "games"),
                   settings.DATA_DIR,
                   join(settings.DATA_DIR, "covers"),
                   settings.ICON_PATH,
                   join(settings.DATA_DIR, "banners"),
                   join(settings.DATA_DIR, "runners"),
                   join(settings.DATA_DIR, "lib"),
                   settings.RUNTIME_DIR,
                   settings.CACHE_DIR,
                   join(settings.CACHE_DIR, "installer"),
                   join(settings.CACHE_DIR, "tmp")]
    for directory in directories:
        if not os.path.exists(directory):
            logger.debug("creating directory %s" % directory)
            os.makedirs(directory)

    if force_wipe:
        os.remove(settings.PGA_DB)
    pga.syncdb()


def read_yaml_from_file(filename):
    """Read filename and return parsed yaml"""
    if not filename or not os.path.exists(filename):
        return {}
    try:
        content = file(filename, 'r').read()
        yaml_content = yaml.load(content) or {}
    except (yaml.scanner.ScannerError, yaml.parser.ParserError):
        logger.error("error parsing file %s", filename)
        yaml_content = {}
    return yaml_content


def write_yaml_to_file(filepath, config):
    if not filepath:
        raise ValueError('Missing filepath')
    yaml_config = yaml.dump(config, default_flow_style=False)
    with open(filepath, "w") as filehandler:
        filehandler.write(yaml_config)


class LutrisConfig(object):
    """Class where all the configuration handling happens.

    Lutris configuration uses a cascading mecanism where
    each higher, more specific level override the lower ones.

    The config files are stored in a YAML format and are easy to edit manually.

    """
    def __init__(self, runner=None, game=None):
        # Initialize configuration
        self.config = {'system': {}}
        self.game_config = {}
        self.runner_config = {}
        self.system_config = {}

        self.game = None  # This is actually a game *slug*
        self.runner = None

        # By default config type is system, it can also be runner and game
        # this means that when you call lutris_config_instance["key"] it will
        # pick up the right configuration depending of config_type
        if game:
            self.game = game
            self.config_type = "game"
        elif runner:
            self.runner = runner
            self.config_type = "runner"
        else:
            self.config_type = "system"

        self.game_config = read_yaml_from_file(self.game_config_path)
        if self.game:
            self.runner = self.game_config.get("runner")
        self.runner_config = read_yaml_from_file(self.runner_config_path)
        self.system_config = read_yaml_from_file(self.system_config_path)
        self.update_global_config()

    @property
    def system_config_path(self):
        return os.path.join(settings.CONFIG_DIR, "system.yml")

    @property
    def runner_config_path(self):
        if not self.runner:
            return
        return os.path.join(settings.CONFIG_DIR, "runners/%s.yml" % self.runner)

    @property
    def game_config_path(self):
        if not self.game:
            return
        return os.path.join(settings.CONFIG_DIR, "games/%s.yml" % self.game)

    def __str__(self):
        return str(self.config)

    def __getitem__(self, key, default=None):
        """Allow to access config data directly by keys."""
        if key in ('game', 'runner', 'system'):
            return self.config.get(key)
        try:
            if self.config_type == "game":
                value = self.game_config[key]
            elif self.config_type == "runner":
                value = self.runner_config[key]
            else:
                value = self.system_config[key]
        except KeyError:
            value = default
        return value

    def __setitem__(self, key, value):
        if self.config_type == "game":
            self.game_config[key] = value
        elif self.config_type == "runner":
            self.runner_config[key] = value
        elif self.config_type == "system":
            self.system_config = value
        self.update_global_config()

    def get(self, key, default=None):
        return self.__getitem__(key, default)

    def update_global_config(self):
        """Update the global config dict."""
        for key in self.system_config.keys():
            if key in self.config:
                self.config[key].update(self.system_config[key])
            else:
                self.config[key] = self.system_config[key]

        for key in self.runner_config.keys():
            if key in self.config:
                self.config[key].update(self.runner_config[key])
            else:
                self.config[key] = self.runner_config[key]

        for key in self.game_config.keys():
            if key in self.config:
                if type(self.config[key]) is dict:
                    self.config[key].update(self.game_config[key])
            else:
                self.config[key] = self.game_config[key]

    def remove(self, game=None):
        """Delete the configuration file from disk."""
        if game is None:
            game = self.game
        logging.debug("removing config for %s", game)
        if os.path.exists(self.game_config_path):
            os.remove(self.game_config_path)
        else:
            logger.debug("No config file at %s" % self.game_config_path)

    def save(self):
        """Save configuration file according to its type"""
        if self.config_type == "system":
            config = self.system_config
            config_path = self.system_config_path
        elif self.config_type == "runner":
            config = self.runner_config
            config_path = self.runner_config_path
        elif self.config_type == "game":
            config = self.game_config
            config_path = self.game_config_path
        else:
            raise ValueError("Invalid config_type '%s'" % self.config_type)
        write_yaml_to_file(config_path, config)
        self.update_global_config()

    def get_path(self, default=None):
        """Get the path to install games for a given runner.

        Return False if it can't find an installation path
        """

        if "system" in self.config and "game_path" in self.config["system"]:
            return self.config["system"]["game_path"]
        if not default or not os.path.exists(default):
            return False
        else:
            return default
