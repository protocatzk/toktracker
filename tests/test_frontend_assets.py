"""
Struktur-Guards für das Frontend.

Sichert ab, dass gemeinsame Helfer nicht wieder dupliziert werden, dass alle Seiten
von `base.html` erben und dass referenzierte Assets tatsächlich existieren.
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import glob
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATIC = os.path.join(ROOT, "static")
TEMPLATES = os.path.join(ROOT, "templates")

SHARED_HELPERS = ("escapeHtml", "fmtEUR", "fmtUSD", "fmtNum", "applyTheme")


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


class TestSharedFrontendHelpers(unittest.TestCase):
    def test_common_js_exists_and_defines_all_helpers(self):
        source = _read(os.path.join(STATIC, "common.js"))
        for helper in SHARED_HELPERS:
            with self.subTest(helper=helper):
                self.assertIn(f"function {helper}(", source)

    def test_helpers_are_not_redefined_in_page_scripts(self):
        offenders = []
        for path in glob.glob(os.path.join(STATIC, "*.js")):
            name = os.path.basename(path)
            if name in ("common.js", "chart.umd.min.js"):
                continue
            source = _read(path)
            for helper in SHARED_HELPERS:
                if re.search(rf"function\s+{helper}\s*\(", source):
                    offenders.append(f"{name}:{helper}")
        self.assertEqual(offenders, [], "Doppelte Helfer-Definitionen: " + ", ".join(offenders))

    def test_common_js_is_loaded_before_page_scripts(self):
        base = _read(os.path.join(TEMPLATES, "base.html"))
        self.assertIn("/static/common.js", base)
        self.assertLess(base.index("common.js"), base.index("</head>"))


class TestTemplatesAndAssets(unittest.TestCase):
    def test_all_pages_extend_base(self):
        for path in glob.glob(os.path.join(TEMPLATES, "*.html")):
            name = os.path.basename(path)
            if name == "base.html":
                continue
            with self.subTest(template=name):
                source = _read(path)
                self.assertTrue(
                    source.lstrip().startswith('{% extends "base.html" %}'),
                    f"{name} erbt nicht von base.html",
                )

    def test_referenced_static_assets_exist(self):
        missing = []
        for path in glob.glob(os.path.join(TEMPLATES, "*.html")):
            source = _read(path)
            for asset in re.findall(r'(?:src|href)="(/static/[^"?]+)', source):
                target = os.path.join(ROOT, asset.lstrip("/"))
                if not os.path.exists(target):
                    missing.append(f"{os.path.basename(path)} -> {asset}")
        self.assertEqual(missing, [], "Fehlende Assets: " + ", ".join(missing))

    def test_no_template_contains_inline_style_block(self):
        offenders = [os.path.basename(p) for p in glob.glob(os.path.join(TEMPLATES, "*.html")) if "<style" in _read(p)]
        self.assertEqual(offenders, [], "Inline-CSS gefunden: " + ", ".join(offenders))

    def test_chart_library_is_only_loaded_once_per_page(self):
        for path in glob.glob(os.path.join(TEMPLATES, "*.html")):
            source = _read(path)
            if os.path.basename(path) == "base.html":
                continue
            with self.subTest(template=os.path.basename(path)):
                self.assertLessEqual(source.count("chart.umd.min.js"), 1)


if __name__ == "__main__":
    unittest.main()
