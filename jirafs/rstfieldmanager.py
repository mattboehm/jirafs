import os
import re

from jirafs import constants


class RSTFieldManager(dict):
    FIELD_MATCHER = re.compile(
        '^%s$' % (
            constants.TICKET_FILE_FIELD_TEMPLATE.replace(
                '{field_name}', '([\w_]+)'
            )
        )
    )

    def __init__(self):
        self._data = self.load()
        super(RSTFieldManager, self).__init__(self._data)

    @classmethod
    def create(cls, folder, revision=None, path=None):
        if revision and path:
            raise TypeError(
                'You may specify a git revision or a local path; not both.'
            )

        if revision:
            return GitRevisionRSTFieldManager(folder, revision)
        else:
            return LocalFileRSTFieldManager(folder, path)

    def get_requested_per_ticket_fields(self):
        return constants.FILE_FIELDS

    def get_used_per_ticket_fields(self):
        raise NotImplementedError()

    def get_fields_from_string(self, string):
        """ Gets field data from an incoming string.

        Parses through the string using the following RST-derived
        pattern::

            0 | FIELD_NAME::
            1 |
            2 |     VALUE

        """
        FIELD_DECLARED = 0
        PREAMBLE = 1
        VALUE = 2

        state = None

        data = {}
        field_name = ''
        value = ''
        if not string:
            return data
        lines = string.split('\n')
        for idx, line in enumerate(lines):
            line = line.replace('\t', '    ')
            if state == FIELD_DECLARED and not line:
                state = PREAMBLE
            elif (
                (state == VALUE or state is None)
                and re.match('^(\w+)::', line)
            ):
                if value:
                    data[field_name] = value.strip()
                    value = ''
                state = FIELD_DECLARED
                field_name = re.match('^(\w+)::', line).group(1)
                if not field_name:
                    raise ValueError(
                        "Syntax error on line %s" % idx
                    )
            elif (state == PREAMBLE or state == VALUE):
                state = VALUE
                value = value + '\n' + line[4:]  # Remove first indentation
        if value:
            data[field_name] = value.strip()

        return data

    def load(self):
        fields = self.get_fields_from_string(
            self.get_file_contents(constants.TICKET_DETAILS)
        )

        used_fields = set(self.get_used_per_ticket_fields())
        requested_fields = set(self.get_requested_per_ticket_fields())

        file_fields = {}
        for field_name in used_fields | requested_fields:
            try:
                field_path = constants.TICKET_FILE_FIELD_TEMPLATE.format(
                    field_name=field_name
                )
                file_fields[field_name] = self.get_file_contents(field_path)
            except (IOError, OSError):
                pass

        fields.update(file_fields)
        return fields


class LocalFileRSTFieldManager(RSTFieldManager):
    def __init__(self, folder, path):
        self.folder = folder
        self.path = path
        super(LocalFileRSTFieldManager, self).__init__()

    def get_file_contents(self, path):
        full_path = os.path.join(self.path, path)

        with open(self.folder.get_local_path(full_path), 'r') as _in:
            return _in.read().strip()

    def get_used_per_ticket_fields(self):
        fields = []
        for filename in os.listdir(self.path):
            full_path = os.path.join(self.path, filename)
            matched = self.FIELD_MATCHER.match(filename)
            if matched and os.path.isfile(full_path):
                field_name = matched.group(1)
                if not field_name in constants.FILE_FIELD_BLACKLIST:
                    fields.append(field_name)

        return fields

    def save(self):
        raise NotImplementedError()


class GitRevisionRSTFieldManager(RSTFieldManager):
    def __init__(self, folder, revision):
        self.folder = folder
        self.revision = revision
        super(GitRevisionRSTFieldManager, self).__init__()

    def get_file_contents(self, path):
        return self.folder.get_local_file_at_revision(
            path,
            self.revision
        )

    def get_used_per_ticket_fields(self):
        files = self.folder.run_git_command(
            'ls-tree',
            '--name-only',
            self.revision
        ).split()
        fields = []

        for filename in files:
            matched = self.FIELD_MATCHER.match(filename)
            if matched:
                field_name = matched.group(1)
                if not field_name in constants.FILE_FIELD_BLACKLIST:
                    fields.append(field_name)

        return fields
