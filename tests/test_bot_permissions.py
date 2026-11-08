"""
Tests für die bot.*-Capabilities und die zentrale Bot-Befehl-Matrix.

Die Tests stellen sicher, dass jeder registrierte Telegram-Befehl in
``BOT_COMMAND_PERMISSIONS`` auftaucht und der zugehörige Handler tatsächlich
die passende ``PERM_BOT_*``-Capability über ``_authorize`` prüft.
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import ast
import pathlib
import unittest

from shared import permissions as permissions_module
from shared.permissions import (
    BOT_COMMAND_ALIASES,
    BOT_COMMAND_PERMISSIONS,
    PERM_BOT_ADMIN_LOGIN,
    PERM_BOT_ANALYTICS_VIEW,
    PERM_BOT_CRM_EDIT,
    PERM_BOT_PUBLIC_VIEW,
    PERM_BOT_RADAR_VIEW,
    PERM_BOT_SETTINGS_MANAGE,
    PERM_BOT_STREAMERS_MANAGE,
    PERM_BOT_SYSTEM_VIEW,
    PERM_BOT_USERS_MANAGE,
    ROLE_ADMIN,
    ROLE_MODERATOR,
    ROLE_USER,
    ROLE_VIEWER,
    bot_command_allowed,
    bot_command_permission,
    bot_commands_for,
    is_known_bot_command,
    normalize_bot_command,
    permissions_for,
)

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
TELEGRAM_SOURCE = PROJECT_ROOT / "telegram_service.py"

# Umkehrung: "bot.analytics.view" -> "PERM_BOT_ANALYTICS_VIEW"
PERMISSION_CONSTANTS = {
    value: name
    for name, value in vars(permissions_module).items()
    if name.startswith("PERM_BOT_") and isinstance(value, str)
}


def _commands_from_node(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, (ast.List, ast.Tuple)):
        return [
            item.value
            for item in node.elts
            if isinstance(item, ast.Constant) and isinstance(item.value, str)
        ]
    return []


def _handler_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def _registered_handlers() -> dict[str, str]:
    """command -> Handler-Methodenname (aus CommandHandler(...)-Aufrufen)."""
    tree = ast.parse(TELEGRAM_SOURCE.read_text(encoding="utf-8"))
    result: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Name) and func.id == "CommandHandler"):
            continue
        if len(node.args) < 2:
            continue
        method = _handler_name(node.args[1])
        if not method:
            continue
        for command in _commands_from_node(node.args[0]):
            result[command] = method
    return result


def _authorize_permissions() -> dict[str, set[str]]:
    """Handler-Methode -> benötigte PERM_BOT_*-Konstanten aus _authorize(...)."""
    tree = ast.parse(TELEGRAM_SOURCE.read_text(encoding="utf-8"))
    result: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        used: set[str] = set()
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            func = child.func
            if not (isinstance(func, ast.Attribute) and func.attr == "_authorize"):
                continue
            for keyword in child.keywords:
                if keyword.arg != "require_permission":
                    continue
                if isinstance(keyword.value, ast.Name):
                    used.add(keyword.value.id)
        result[node.name] = used
    return result


class TestBotCommandMatrix(unittest.TestCase):
    def test_aliases_resolve_to_canonical_commands(self):
        self.assertEqual(normalize_bot_command("/start"), "help")
        self.assertEqual(normalize_bot_command("geschenke"), "gifts")
        self.assertEqual(normalize_bot_command("@TokTrackerBot"), None)
        self.assertEqual(normalize_bot_command("/frontenwechsler"), "loyalty")
        self.assertTrue(is_known_bot_command("alerts"))
        self.assertFalse(is_known_bot_command("unbekannt"))

    def test_unknown_command_is_fail_closed(self):
        self.assertFalse(bot_command_allowed("unbekannt", ROLE_ADMIN))
        self.assertIsNone(bot_command_permission("unbekannt"))

    def test_registered_commands_have_a_registry_entry(self):
        for command, method in _registered_handlers().items():
            with self.subTest(command=command, method=method):
                self.assertTrue(
                    is_known_bot_command(command),
                    f"CommandHandler für /{command} fehlt in BOT_COMMAND_PERMISSIONS",
                )

    def test_handlers_check_their_declared_permission(self):
        handlers = _registered_handlers()
        used_permissions = _authorize_permissions()
        for command, method in handlers.items():
            canonical = normalize_bot_command(command)
            required = BOT_COMMAND_PERMISSIONS[canonical]
            with self.subTest(command=command, method=method, permission=required):
                if required is None:
                    self.assertFalse(
                        used_permissions.get(method),
                        f"{method} sollte keine Capability verlangen",
                    )
                    continue
                expected_constant = PERMISSION_CONSTANTS[required]
                self.assertIn(
                    expected_constant,
                    used_permissions.get(method, set()),
                    f"{method} prüft {expected_constant} nicht über _authorize()",
                )

    def test_interactive_callbacks_are_guarded(self):
        tree = ast.parse(TELEGRAM_SOURCE.read_text(encoding="utf-8"))
        source = TELEGRAM_SOURCE.read_text(encoding="utf-8")
        callback = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "_on_interactive_callback"
        )
        callback_source = ast.unparse(callback) if hasattr(ast, "unparse") else source
        # _on_interactive_callback nutzt permissions_for() statt _authorize();
        # deshalb prüfen wir die verwendeten Konstanten direkt im Quelltext.
        self.assertIn("access.get(\"allowed\")", source)
        for permission in (
            PERM_BOT_ANALYTICS_VIEW,
            PERM_BOT_RADAR_VIEW,
            PERM_BOT_CRM_EDIT,
        ):
            constant = PERMISSION_CONSTANTS[permission]
            with self.subTest(constant=constant):
                self.assertIn(constant, callback_source)


class TestBotRoleMatrix(unittest.TestCase):
    def test_viewer_gets_public_bot_commands_only(self):
        commands = set(bot_commands_for(ROLE_VIEWER))
        self.assertIn("help", commands)
        self.assertIn("streamers", commands)
        self.assertIn("gifts", commands)
        self.assertNotIn("overview", commands)
        self.assertNotIn("radar", commands)
        self.assertNotIn("users", commands)

    def test_user_additionally_gets_radar_commands(self):
        commands = set(bot_commands_for(ROLE_USER))
        self.assertTrue({"radar", "whales", "donor", "vip", "loyalty"} <= commands)
        self.assertNotIn("overview", commands)
        self.assertNotIn("users", commands)

    def test_moderator_gets_analytics_and_status(self):
        commands = set(bot_commands_for(ROLE_MODERATOR))
        self.assertTrue({"overview", "report", "streamer", "status"} <= commands)
        self.assertNotIn("users", commands)
        self.assertNotIn("mode", commands)
        self.assertNotIn("login", commands)

    def test_admin_gets_every_bot_command(self):
        commands = set(bot_commands_for(ROLE_ADMIN))
        self.assertEqual(commands, set(BOT_COMMAND_PERMISSIONS))

    def test_blocked_user_keeps_only_unchecked_commands(self):
        commands = set(bot_commands_for(ROLE_ADMIN, -1))
        self.assertEqual(commands, {"whoami"})
        self.assertTrue(bot_command_allowed("id", ROLE_ADMIN, -1))
        self.assertFalse(bot_command_allowed("overview", ROLE_ADMIN, -1))

    def test_bot_only_capabilities_do_not_leak_from_web_role(self):
        # Moderator hat analytics.view im Web, aber die Bot-Capability ist separat.
        self.assertIn(PERM_BOT_ANALYTICS_VIEW, permissions_for(ROLE_MODERATOR))
        self.assertNotIn(PERM_BOT_USERS_MANAGE, permissions_for(ROLE_MODERATOR))
        self.assertNotIn(PERM_BOT_SETTINGS_MANAGE, permissions_for(ROLE_MODERATOR))
        self.assertIn(PERM_BOT_ADMIN_LOGIN, permissions_for(ROLE_ADMIN))
        self.assertNotIn(PERM_BOT_ADMIN_LOGIN, permissions_for(ROLE_MODERATOR))

    def test_registry_contains_stream_alert_command(self):
        # /alert gehört zum Stream-Alert-Feature und ist bereits vorgesehen.
        self.assertEqual(
            BOT_COMMAND_PERMISSIONS["alert"],
            PERM_BOT_STREAMERS_MANAGE,
        )


if __name__ == "__main__":
    unittest.main()
