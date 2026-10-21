"""No real Keychain query: Security calls are replaced before every test read."""
from contextlib import contextmanager
import ctypes as C
import io
import os
import sys
import unittest
from unittest.mock import Mock, patch

from buzz_agent_bridge import cli, keychain, secret_launcher


class KeychainTests(unittest.TestCase):
    def test_only_two_dedicated_items_are_requested(self):
        calls = []
        fixture = {"storage_key": bytes(range(32)).hex(),
                   "mcp_token": "synthetic-fixture-not-a-credential"}

        class Reader:
            @contextmanager
            def session(self):
                yield self

            def read(self, service, account):
                calls.append((service, account))
                return fixture[account]

        with patch.object(keychain, "_MacKeychain", Reader):
            self.assertEqual(keychain.read_keychain_secrets("buzz-agent-bridge.fixture"), fixture)
        self.assertEqual(calls, [("buzz-agent-bridge.fixture", "storage_key"),
                                 ("buzz-agent-bridge.fixture", "mcp_token")])

    def test_unrelated_and_wildcard_services_never_load_frameworks(self):
        with patch.object(keychain, "_MacKeychain", side_effect=AssertionError("No access")):
            for value in ("buzz-desktop", "secrets", "", "buzz-agent-bridge.*",
                          "buzz-agent-bridge.", "buzz-agent-bridge.foo\n", None):
                with self.assertRaises(keychain.KeychainReadError):
                    keychain.read_keychain_secrets(value)

    def test_unsupported_os_fails_before_loading_frameworks(self):
        with patch.object(sys, "platform", "linux"), \
                patch.object(keychain.C, "CDLL", side_effect=AssertionError("No library load")):
            with self.assertRaisesRegex(keychain.KeychainReadError, "requires macOS"):
                keychain.read_keychain_secrets("buzz-agent-bridge.fixture")

    def test_partial_read_failure_does_not_start_host_or_use_environment(self):
        reader = Mock()
        reader.session.return_value.__enter__ = Mock(return_value=reader)
        reader.session.return_value.__exit__ = Mock(return_value=False)
        reader.read.side_effect = [bytes(range(32)).hex(), RuntimeError("sensitive-native-fixture")]
        output = io.StringIO()
        with patch.object(keychain, "_MacKeychain", return_value=reader), \
                patch.object(cli, "load", return_value={}), \
                patch.object(secret_launcher, "launch_host") as launch, \
                patch.dict(os.environ, {"BRIDGE_STORAGE_KEY": "must-not-fallback",
                                        "BRIDGE_MCP_TOKEN": "must-not-fallback"}), \
                patch.object(sys, "argv", ["bridge", "host-keychain", "--config", "/fixture.json",
                                           "--service", "buzz-agent-bridge.fixture"]), \
                patch.object(sys, "stderr", output), patch.object(sys, "stdout", output):
            self.assertEqual(cli.main(), 1)
            launch.assert_not_called()
        self.assertNotIn("sensitive-native-fixture", output.getvalue())
        self.assertNotIn(bytes(range(32)).hex(), output.getvalue())
        self.assertIn("no fallback", output.getvalue())

    def test_native_session_refuses_locked_keychain_and_restores_process_ui(self):
        for unlocked in (False, True):
            for fail_read in (False, True):
                calls = []

                class Security:
                    def SecKeychainGetUserInteractionAllowed(self, out):
                        out._obj.value = 1
                        return 0

                    def SecKeychainSetUserInteractionAllowed(self, value):
                        calls.append(("ui", int(value)))
                        return 0

                    def SecKeychainCopyDefault(self, out):
                        out._obj.value = 123
                        calls.append(("default",))
                        return 0

                    def SecKeychainGetStatus(self, reference, out):
                        out._obj.value = 3 if unlocked else 2
                        return 0

                native = object.__new__(keychain._MacKeychain)
                native.sec, native.cf, native.keychain = Security(), Mock(), None
                entered = False
                try:
                    with native.session():
                        entered = True
                        if fail_read:
                            raise keychain.KeychainReadError("synthetic failure")
                except keychain.KeychainReadError:
                    pass
                self.assertEqual(entered, unlocked)
                self.assertEqual(calls, [("ui", 0), ("default",), ("ui", 1)])
                self.assertIsNone(native.keychain)
                native.cf.CFRelease.assert_called_once()

    def test_status_errors_are_fixed_and_do_not_retry(self):
        for status in (-25300, -25308, -25293, -128, -25291, 123):
            with self.assertRaises(keychain.KeychainReadError):
                keychain._check(status)

    @unittest.skipUnless(sys.platform == "darwin", "CoreFoundation ABI test requires macOS")
    def test_native_query_uses_exact_filters_and_mocked_security_response(self):
        # Load framework symbols and construct CF values only. Never call session(),
        # SecKeychainCopyDefault, SecKeychainGetStatus or the real SecItemCopyMatching.
        native = keychain._MacKeychain()
        cf, real_sec = native.cf, native.sec
        native._bind(cf, "CFDictionaryGetCount", C.c_long, [C.c_void_p])
        native._bind(cf, "CFDictionaryGetValue", C.c_void_p, [C.c_void_p, C.c_void_p])
        native._bind(cf, "CFStringGetCString", C.c_ubyte,
                     [C.c_void_p, C.c_void_p, C.c_long, C.c_uint32])
        native._bind(cf, "CFArrayGetCount", C.c_long, [C.c_void_p])
        native._bind(cf, "CFArrayGetValueAtIndex", C.c_void_p, [C.c_void_p, C.c_long])
        native._bind(cf, "CFDataCreate", C.c_void_p, [C.c_void_p, C.c_char_p, C.c_long])
        native._constant = lambda name: C.c_void_p.in_dll(
            cf if name.startswith("kCF") else real_sec, name).value
        native.keychain = cf.CFStringCreateWithCString(None, b"mock-keychain-reference", 0x08000100)
        calls = []

        def matching(query, out):
            calls.append(query)
            self.assertEqual(cf.CFDictionaryGetCount(query), 8)

            def value(name):
                return cf.CFDictionaryGetValue(query, native._constant(name))

            for name, expected in (("kSecAttrService", b"buzz-agent-bridge.fixture"),
                                   ("kSecAttrAccount", b"storage_key")):
                buffer = C.create_string_buffer(128)
                self.assertTrue(cf.CFStringGetCString(value(name), buffer, len(buffer), 0x08000100))
                self.assertEqual(buffer.value, expected)
            for name, expected in (("kSecClass", "kSecClassGenericPassword"),
                                   ("kSecMatchLimit", "kSecMatchLimitOne"),
                                   ("kSecAttrSynchronizable", "kCFBooleanFalse"),
                                   ("kSecReturnData", "kCFBooleanTrue"),
                                   ("kSecUseAuthenticationUI", "kSecUseAuthenticationUIFail")):
                self.assertEqual(value(name), native._constant(expected))
            self.assertEqual(cf.CFArrayGetCount(value("kSecMatchSearchList")), 1)
            self.assertEqual(cf.CFArrayGetValueAtIndex(value("kSecMatchSearchList"), 0), native.keychain)
            result = b"synthetic-result"
            out._obj.value = cf.CFDataCreate(None, result, len(result))
            return 0

        native.sec = Mock(SecItemCopyMatching=matching)
        try:
            self.assertEqual(native.read("buzz-agent-bridge.fixture", "storage_key"), "synthetic-result")
            self.assertEqual(len(calls), 1)
        finally:
            cf.CFRelease(native.keychain)
