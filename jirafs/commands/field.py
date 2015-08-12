import json

from jirafs.exceptions import JirafsError
from jirafs.plugin import CommandPlugin


class Command(CommandPlugin):
    """ Get the status of the current ticketfolder """
    TRY_SUBFOLDERS = True
    MIN_VERSION = '1.0a1'
    MAX_VERSION = '1.99.99'

    def handle(self, args, folder, **kwargs):
        return self.field(
            folder, args.field_name, raw=args.raw, formatted=args.formatted
        )

    def add_arguments(self, parser):
        parser.add_argument(
            '--raw',
            help=(
                'Return the field value without applying '
                'plugin transformations'
            ),
            action='store_true',
            default=False
        )
        parser.add_argument(
            '--formatted',
            help=(
                'Format JSON output with indentation and sorted keys.'
            ),
            action='store_true',
            default=False
        )
        parser.add_argument(
            'field_name',
        )

    def field(self, folder, field_name, raw=False, formatted=False):
        fields = folder.get_fields()

        key_dotpath = None
        if '.' in field_name:
            field_name, key_dotpath = field_name.split('.', 1)

        if field_name not in fields:
            raise JirafsError("Field '%s' does not exist." % field_name)

        if raw:
            data = fields[field_name]
        else:
            data = fields.get_transformed(field_name)

        if key_dotpath:
            try:
                for component in key_dotpath.split('.'):
                    if component not in data:
                        data = None
                        break
                    data = data[component]
            except (ValueError, TypeError):
                raise JirafsError(
                    "Field '%s' could not be parsed as JSON for retrieving "
                    "dotpath '%s'." % (
                        field_name,
                        key_dotpath,
                    )
                )

        if isinstance(data, (list, dict)):
            kwargs = {}
            if formatted:
                kwargs = {
                    'indent': 4,
                    'sort_keys': True,
                }
            data = json.dumps(data, **kwargs)

        print(data)
