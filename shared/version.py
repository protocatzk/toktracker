"""
Zentrale Versionsangabe der Anwendung.

Single Source of Truth für die Produktversion. Sie wird im Footer, im
Healthcheck (`/api/health`) und in der Release-Tagging-Doku verwendet.
Asset-Cache-Token (`static/*.js?v=…`) sind davon unabhängig und zählen
pro Datei hoch.
"""

__version__ = "3.0.0"

# Kurzform für Badges/Clients, z.B. "3.0.0".
VERSION = __version__
