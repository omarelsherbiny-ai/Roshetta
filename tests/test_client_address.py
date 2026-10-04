# tests/test_client_address.py
import unittest
from types import SimpleNamespace

from server.app.config import Settings
from server.app.services.client_address import client_address, resolve_client_address


def request(peer, forwarded=None):
    headers = {"x-forwarded-for": forwarded} if forwarded is not None else {}
    return SimpleNamespace(client=SimpleNamespace(host=peer) if peer else None, headers=headers)


class ClientAddressTests(unittest.TestCase):
    PROXY = {"127.0.0.1", "10.0.0.2"}

    def test_without_trusted_proxies_the_header_is_ignored(self):
        self.assertEqual(resolve_client_address("198.51.100.9", "203.0.113.5", set()), "198.51.100.9")

    def test_a_peer_that_is_not_a_proxy_cannot_name_the_client(self):
        self.assertEqual(resolve_client_address("198.51.100.9", "203.0.113.5", self.PROXY), "198.51.100.9")

    def test_a_trusted_proxy_names_the_real_client(self):
        self.assertEqual(resolve_client_address("127.0.0.1", "203.0.113.5", self.PROXY), "203.0.113.5")

    def test_a_fake_first_entry_is_not_believed(self):
        self.assertEqual(resolve_client_address("127.0.0.1", "1.1.1.1, 203.0.113.5", self.PROXY), "203.0.113.5")

    def test_other_trusted_proxies_in_the_chain_are_skipped(self):
        self.assertEqual(resolve_client_address("127.0.0.1", "203.0.113.5, 10.0.0.2", self.PROXY), "203.0.113.5")

    def test_a_malformed_chain_or_an_empty_header_falls_back_to_the_peer(self):
        self.assertEqual(resolve_client_address("127.0.0.1", "not-an-ip", self.PROXY), "127.0.0.1")
        self.assertEqual(resolve_client_address("127.0.0.1", "203.0.113.5, junk", self.PROXY), "127.0.0.1")
        self.assertEqual(resolve_client_address("127.0.0.1", "", self.PROXY), "127.0.0.1")
        self.assertEqual(resolve_client_address("127.0.0.1", "10.0.0.2", self.PROXY), "127.0.0.1")

    def test_ipv6_clients_work(self):
        self.assertEqual(resolve_client_address("127.0.0.1", "2001:db8::1", self.PROXY), "2001:db8::1")

    def test_request_wrapper_handles_a_missing_peer_and_the_setting(self):
        self.assertEqual(client_address(request(None), set()), "unknown")
        self.assertEqual(client_address(request("127.0.0.1", "203.0.113.5"), self.PROXY), "203.0.113.5")
        parsed = Settings(TRUSTED_PROXY_IPS=" 127.0.0.1, ::1 ,").trusted_proxy_list
        self.assertEqual(parsed, {"127.0.0.1", "::1"})
        self.assertEqual(Settings(TRUSTED_PROXY_IPS="").trusted_proxy_list, set())


if __name__ == "__main__":
    unittest.main()