from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from plane.app.orchestrator.tools import CyrusToolError, TOOL_REGISTRY, execute_tool


class Command(BaseCommand):
    help = "Run a Cyrus orchestrator tool via JSON arguments"

    def add_arguments(self, parser):
        parser.add_argument("tool_name", choices=sorted(TOOL_REGISTRY.keys()))
        parser.add_argument("json_args", nargs="?", default="{}")

    def handle(self, *args, **options):
        try:
            parsed_args = json.loads(options["json_args"] or "{}")
        except json.JSONDecodeError as exc:
            raise CommandError(f"json_args must be valid JSON: {exc}") from exc
        if not isinstance(parsed_args, dict):
            raise CommandError("json_args must decode to a JSON object")
        try:
            result = execute_tool(options["tool_name"], parsed_args)
        except CyrusToolError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, indent=2, sort_keys=True))
