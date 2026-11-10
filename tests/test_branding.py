"""Guards für das TT-INTELLIGENCE-Branding.

Sichert ab, dass die sichtbare Marke zentral definiert ist, die Mini-App
das Industrial-Design lädt und technische Bezeichner (Cookies, Storage-Keys)
aus Kompatibilitätsgründen unverändert bleiben.
"""

import os
import unittest

from shared import bot_format as bf
from shared.branding import (
    BRAND_LEGACY,
    BRAND_NAME,
    BRAND_SHORT,
    BRAND_TAGLINE,
    LEGACY_SESSION_COOKIE,
    LEGACY_STORAGE_PREFIX,
)

ROOT = os.environ.get("TOKTRACKER_PROJECT_ROOT") or os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)


def _read(*parts: str) -> str:
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


class TestBrandingConstants(unittest.TestCase):
    def test_brand_is_uppercase(self):
        self.assertEqual(BRAND_NAME, "TT-INTELLIGENCE")
        self.assertEqual(BRAND_SHORT, "TT-I")
        self.assertEqual(BRAND_TAGLINE, "LIVE EARNINGS INTELLIGENCE")
        self.assertEqual(BRAND_LEGACY, "toktracker")

    def test_technical_identifiers_are_unchanged(self):
        self.assertEqual(LEGACY_SESSION_COOKIE, "toktracker_session")
        self.assertEqual(LEGACY_STORAGE_PREFIX, "toktracker_")


class TestMiniAppBranding(unittest.TestCase):
    def test_miniapp_uses_shared_tokens(self):
        base = _read("templates", "base.html")
        self.assertIn("static/brand.css", base)
        template = _read("templates", "miniapp.html")
        self.assertIn('{% extends "base.html" %}', template)
        self.assertIn("brand_wordmark", template)
        self.assertIn("brand_tagline", template)
        self.assertNotIn("toktracker Mini-App", template)

    def test_miniapp_keeps_legacy_storage_key(self):
        script = _read("static", "miniapp.js")
        self.assertIn('"toktracker_admin_token"', script)

    def test_miniapp_is_dark_only(self):
        styles = _read("static", "miniapp.css")
        self.assertNotIn('[data-theme="light"]', styles)


class TestGlobalDesignSystem(unittest.TestCase):
    def test_base_loads_brand_css_before_page_styles(self):
        base = _read("templates", "base.html")
        self.assertIn("static/brand.css", base)
        self.assertIn("static/common.js", base)
        self.assertLess(base.index("brand.css"), base.index("common.js"))

    def test_brand_css_defines_light_theme_and_fonts(self):
        styles = _read("static", "brand.css")
        self.assertIn('[data-theme="light"]', styles)
        self.assertIn("@font-face", styles)
        self.assertIn("fonts/inter-latin-var.woff2", styles)
        self.assertIn("fonts/jetbrains-mono-latin-var.woff2", styles)

    def test_visible_legacy_name_is_gone_from_templates(self):
        import re
        offenders = []
        for name in os.listdir(os.path.join(ROOT, "templates")):
            if not name.endswith(".html"):
                continue
            source = _read("templates", name)
            if re.search(r"toktracker(?!_)", source, re.IGNORECASE):
                offenders.append(name)
        self.assertEqual(offenders, [], "Sichtbarer Legacy-Name: " + ", ".join(offenders))

    def test_shared_app_header_is_used_by_internal_pages(self):
        for name in (
            "index.html",
            "public.html",
            "stats.html",
            "access.html",
            "donor_radar.html",
            "chat_intelligence.html",
            "site_analytics.html",
        ):
            with self.subTest(template=name):
                source = _read("templates", name)
                self.assertIn("partials/app_header.html", source)
                self.assertIn("app_header(", source)



class TestBotFormatting(unittest.TestCase):
    def test_header_uses_brand_and_escapes(self):
        out = bf.header(1, "Finanzen")
        self.assertIn("TT-INTELLIGENCE", out)
        self.assertIn("01 / FINANZEN", out)

    def test_kv_table_is_monospace_and_escaped(self):
        out = bf.kv_table([("NETTO", "€ 1,00"), ("NAME", "<script>")])
        self.assertTrue(out.startswith("<pre>"))
        self.assertIn("NETTO", out)
        self.assertIn("&lt;script&gt;", out)

    def test_chunking_keeps_messages_below_limit(self):
        text = "\n\n".join(f"Absatz {i} " + ("x" * 500) for i in range(20))
        chunks = bf.chunk_message(text, limit=1000)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 1000 for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
