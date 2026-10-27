"""
Tests für das Docker-Monitoring: Zugriff läuft über den Socket-Proxy (TCP),
mit UDS-Fallback und sauberem "nicht verfügbar"-Verhalten.
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import unittest

import system_service


class TestDockerClientSelection(unittest.TestCase):
    def setUp(self):
        self._proxy = system_service.DOCKER_PROXY_URL
        self._socket = system_service.DOCKER_SOCKET_PATH

    def tearDown(self):
        system_service.DOCKER_PROXY_URL = self._proxy
        system_service.DOCKER_SOCKET_PATH = self._socket

    def test_proxy_url_is_preferred(self):
        system_service.DOCKER_PROXY_URL = "http://docker-socket-proxy:2375"
        system_service.DOCKER_SOCKET_PATH = "/var/run/docker.sock"

        client, endpoint = system_service._build_docker_client()
        try:
            self.assertIsNotNone(client)
            self.assertEqual(endpoint, "proxy:http://docker-socket-proxy:2375")
            self.assertEqual(str(client.base_url).rstrip("/"), "http://docker-socket-proxy:2375")
        finally:
            if client is not None:
                client.close()

    def test_socket_fallback_when_no_proxy_configured(self):
        import os
        import tempfile

        # Nur die Existenz des Socket-Pfads wird geprüft – eine echte Verbindung
        # wird im Test nicht aufgebaut.
        handle, socket_path = tempfile.mkstemp(prefix="fake-docker-", suffix=".sock")
        os.close(handle)
        system_service.DOCKER_PROXY_URL = ""
        system_service.DOCKER_SOCKET_PATH = socket_path

        client, endpoint = system_service._build_docker_client()
        try:
            self.assertEqual(endpoint, f"unix:{socket_path}")
            self.assertIsNotNone(client)
        finally:
            if client is not None:
                client.close()
            os.unlink(socket_path)

    def test_unavailable_without_any_configuration(self):
        system_service.DOCKER_PROXY_URL = ""
        system_service.DOCKER_SOCKET_PATH = "/definitiv/nicht/vorhanden.sock"

        client, endpoint = system_service._build_docker_client()
        self.assertIsNone(client)
        self.assertEqual(endpoint, "")

    def test_metrics_report_unavailable_instead_of_raising(self):
        system_service.DOCKER_PROXY_URL = ""
        system_service.DOCKER_SOCKET_PATH = "/definitiv/nicht/vorhanden.sock"

        metrics = system_service._fetch_docker_metrics()
        self.assertFalse(metrics["available"])
        self.assertIn("DOCKER_PROXY_URL", metrics["error"])
        self.assertEqual(metrics["containers"], [])


if __name__ == "__main__":
    unittest.main()
