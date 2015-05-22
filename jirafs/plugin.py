import argparse
import json
import logging
import os
import sys

import six
from verlib import NormalizedVersion

from . import __version__


logger = logging.getLogger(__name__)


class PluginError(Exception):
    pass


class PluginValidationError(PluginError):
    pass


class PluginOperationError(PluginError):
    pass


class JirafsPluginBase(object):
    MIN_VERSION = None
    MAX_VERSION = None

    def validate(self, **kwargs):
        if not self.MIN_VERSION or not self.MAX_VERSION:
            raise PluginValidationError(
                "Minimum and maximum version numbers not specified."
            )

        min_version = NormalizedVersion(self.MIN_VERSION)
        max_version = NormalizedVersion(self.MAX_VERSION)
        curr_version = NormalizedVersion(__version__)
        if not min_version <= curr_version <= max_version:
            raise PluginValidationError(
                "Plugin '%s' is not compatible with version %s of Jirafs; "
                "minimum version: %s; maximum version %s.",
                (
                    self.plugin_name,
                    __version__,
                    self.MIN_VERSION,
                    self.MAX_VERSION,
                ),
            )

        return True


class Plugin(JirafsPluginBase):
    def __init__(self, ticketfolder, plugin_name, **kwargs):
        self.ticketfolder = ticketfolder
        self.plugin_name = plugin_name

    @property
    def metadata_filename(self):
        return self.ticketfolder.get_metadata_path(
            'plugin_meta',
            '%s.json' % self.plugin_name,
        )

    def get_configuration(self):
        config = self.ticketfolder.get_config()
        if config.has_section(self.plugin_name):
            return dict(config.items(self.plugin_name))
        return {}

    def get_metadata(self):
        try:
            with open(self.metadata_filename, 'r') as _in:
                return json.loads(_in.read())
        except (IOError, OSError):
            return {}

    def set_metadata(self, data):
        with open(self.metadata_filename, 'w') as out:
            out.write(
                json.dumps(
                    data,
                    indent=4,
                    sort_keys=True,
                )
            )


class CommandPlugin(JirafsPluginBase):
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def truncate_field_value(self, original_value, length=30):
        value = six.u(original_value).strip()
        for newline in ('\n', '\r'):
            if newline in value:
                value = value[0:value.find(newline)]

        value = value[0:length]

        if value != original_value:
            value = value[0:length-1] + u'\u2026'

        return value

    def get_description(self):
        try:
            return self.__doc__.strip()
        except AttributeError:
            raise None

    def add_arguments(self, parser):
        pass

    def parse_arguments(self, parser, extra_args):
        return parser.parse_args(extra_args)

    @classmethod
    def execute_command(cls, extra_args, jira, path, command_name, **ckwargs):
        from .ticketfolder import TicketFolder
        cmd = cls(
            plugin_name=command_name
        )

        parser = argparse.ArgumentParser(
            prog=os.path.basename(sys.argv[0]) + ' ' + command_name,
            description=cmd.get_description(),
        )
        if cmd.auto_instantiate_folder():
            parser.add_argument(
                '--no-migrate',
                dest='migrate',
                default=True,
                action='store_false'
            )
        cmd.add_arguments(parser)
        args = cmd.parse_arguments(parser, extra_args)

        folder = None
        folder_plugins = []
        if cmd.auto_instantiate_folder():
            folder = TicketFolder(path, jira, migrate=args.migrate)
            folder_plugins = folder.plugins

        kwargs = {
            'args': args,
            'folder': folder,
            'jira': jira,
            'path': path,
            'parser': parser,
        }
        pre_method = 'pre_%s' % command_name
        post_method = 'post_%s' % command_name
        for plugin in folder_plugins:
            if not hasattr(plugin, pre_method):
                continue
            method = getattr(plugin, pre_method)
            result = method(**kwargs)
            if result is not None:
                kwargs = result

        cmd.validate(**kwargs)
        result = cmd.handle(**kwargs)

        for plugin in folder_plugins:
            if not hasattr(plugin, post_method):
                continue
            method = getattr(plugin, post_method)
            post_result = method(result)
            if post_result is not None:
                result = post_result

        if getattr(cls, 'RUN_FOR_SUBTASKS', False):
            for subfolder in folder.subtasks:
                try:
                    cls.execute_command(
                        extra_args,
                        jira,
                        subfolder.path,
                        command_name,
                        **ckwargs
                    )
                except Exception as e:
                    logger.exception(
                        "Exception encountered while running "
                        "'%s' for ticket subfolder '%s': %s" % (
                            command_name,
                            subfolder.ticket_number,
                            e
                        )
                    )

        return result

    def handle(self, folder, args, **kwargs):
        raise NotImplementedError()

    def try_subfolders(self):
        return getattr(self, 'TRY_SUBFOLDERS', False)

    def auto_instantiate_folder(self):
        return getattr(
            self,
            'AUTOMATICALLY_INSTANTIATE_FOLDER',
            True,
        )
