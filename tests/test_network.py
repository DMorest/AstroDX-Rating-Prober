import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.network import make_session, normalize_network_mode, SYSTEM_PROXY, DIRECT, CUSTOM_PROXY

class NetworkTests(unittest.TestCase):
    def test_mode_aliases(self):
        self.assertEqual(normalize_network_mode("跟随系统代理"), SYSTEM_PROXY)
        self.assertEqual(normalize_network_mode("直连（忽略代理）"), DIRECT)
        self.assertEqual(normalize_network_mode("自定义 HTTP(S) 代理"), CUSTOM_PROXY)

    def test_direct_ignores_environment_proxy(self):
        with make_session(DIRECT) as session:
            self.assertFalse(session.trust_env)

    def test_system_proxy_uses_environment(self):
        with make_session(SYSTEM_PROXY) as session:
            self.assertTrue(session.trust_env)

    def test_custom_proxy_explicitly_overrides_environment(self):
        with make_session(CUSTOM_PROXY, "http://127.0.0.1:7890") as session:
            self.assertFalse(session.trust_env)
            self.assertEqual(session.proxies["http"], "http://127.0.0.1:7890")
            self.assertEqual(session.proxies["https"], "http://127.0.0.1:7890")

    def test_custom_proxy_requires_http_url(self):
        with self.assertRaises(ValueError):
            make_session(CUSTOM_PROXY, "127.0.0.1:7890")

if __name__ == "__main__":
    unittest.main()
