from django.core.management.base import BaseCommand

from bugsink.mcp_server import run_mcp_server


class Command(BaseCommand):
    help = "Run the Bugsink MCP server."

    def add_arguments(self, parser):
        parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
        parser.add_argument("--port", type=int, default=8100, help="Bind port (default: 8100)")
        parser.add_argument("--path", default="/mcp", help="MCP endpoint path (default: /mcp)")

    def handle(self, *args, **options):
        run_mcp_server(host=options["host"], port=options["port"], path=options["path"])
