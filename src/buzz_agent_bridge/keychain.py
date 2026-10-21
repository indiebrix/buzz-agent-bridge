"""Opt-in, exact-item macOS reader. No enumeration, creation, unlock, or fallback."""
from contextlib import contextmanager
import ctypes as C
import re
import sys
import threading

from .config import validate_secrets

ACCOUNTS = ("storage_key", "mcp_token")
_LOCK = threading.Lock()


class KeychainReadError(RuntimeError):
    """A fixed diagnostic without item values or native error text."""


def validate_service(service):
    if not isinstance(service, str) or not re.fullmatch(
            r"buzz-agent-bridge\.[a-z0-9][a-z0-9.-]{0,63}", service):
        raise KeychainReadError("Use a dedicated buzz-agent-bridge.<deployment> service.")
    return service


def _check(status):
    if status == 0:
        return
    if status == -25300:
        raise KeychainReadError("A dedicated bridge Keychain item was not found.")
    if status in (-128, -25293, -25308):
        raise KeychainReadError("Keychain access is locked or denied; no fallback was used.")
    raise KeychainReadError("Keychain access is unavailable; no fallback was used.")


class _MacKeychain:
    """Security.framework reads from the current default file-based Keychain.

    SecItemCopyMatching performs the exact query. Legacy compatibility calls limit
    the search and disable optional UI for this process, restoring it afterward.
    They do not change persistent ACLs or OS-wide authentication settings.
    """
    def __init__(self):
        if sys.platform != "darwin":
            raise KeychainReadError("This optional adapter requires macOS.")
        self.cf = C.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        self.sec = C.CDLL("/System/Library/Frameworks/Security.framework/Security")
        pointer = C.c_void_p
        self._bind(self.cf, "CFRelease", None, [pointer])
        self._bind(self.cf, "CFStringCreateWithCString", pointer,
                   [pointer, C.c_char_p, C.c_uint32])
        self._bind(self.cf, "CFArrayCreate", pointer,
                   [pointer, C.POINTER(pointer), C.c_long, pointer])
        self._bind(self.cf, "CFDictionaryCreate", pointer,
                   [pointer, C.POINTER(pointer), C.POINTER(pointer), C.c_long, pointer, pointer])
        self._bind(self.cf, "CFGetTypeID", C.c_ulong, [pointer])
        self._bind(self.cf, "CFDataGetTypeID", C.c_ulong, [])
        self._bind(self.cf, "CFDataGetLength", C.c_long, [pointer])
        self._bind(self.cf, "CFDataGetBytePtr", pointer, [pointer])
        self._bind(self.sec, "SecKeychainGetUserInteractionAllowed", C.c_int32,
                   [C.POINTER(C.c_ubyte)])
        self._bind(self.sec, "SecKeychainSetUserInteractionAllowed", C.c_int32, [C.c_ubyte])
        self._bind(self.sec, "SecKeychainCopyDefault", C.c_int32, [C.POINTER(pointer)])
        self._bind(self.sec, "SecKeychainGetStatus", C.c_int32,
                   [pointer, C.POINTER(C.c_uint32)])
        self._bind(self.sec, "SecItemCopyMatching", C.c_int32, [pointer, C.POINTER(pointer)])
        self.keychain = None

    @staticmethod
    def _bind(library, name, result, args):
        function = getattr(library, name)
        function.restype, function.argtypes = result, args

    def _constant(self, name):
        library = self.cf if name.startswith("kCF") else self.sec
        return C.c_void_p.in_dll(library, name).value

    def _callbacks(self, name):
        return C.addressof((C.c_byte * 1).in_dll(self.cf, name))

    @contextmanager
    def session(self):
        with _LOCK:
            previous = C.c_ubyte()
            _check(self.sec.SecKeychainGetUserInteractionAllowed(C.byref(previous)))
            _check(self.sec.SecKeychainSetUserInteractionAllowed(False))
            reference = C.c_void_p()
            try:
                _check(self.sec.SecKeychainCopyDefault(C.byref(reference)))
                if not reference.value:
                    raise KeychainReadError("The default Keychain is unavailable.")
                flags = C.c_uint32()
                _check(self.sec.SecKeychainGetStatus(reference, C.byref(flags)))
                if flags.value & 3 != 3:
                    raise KeychainReadError("The default Keychain is locked or unreadable.")
                self.keychain = reference.value
                yield self
            finally:
                self.keychain = None
                if reference.value:
                    self.cf.CFRelease(reference)
                _check(self.sec.SecKeychainSetUserInteractionAllowed(previous.value))

    def read(self, service, account):
        validate_service(service)
        if account not in ACCOUNTS or not self.keychain:
            raise KeychainReadError("Keychain item scope was rejected.")
        owned, result = [], C.c_void_p()

        def keep(value):
            if not value:
                raise KeychainReadError("Keychain query allocation failed.")
            owned.append(value)
            return value

        try:
            strings = [keep(self.cf.CFStringCreateWithCString(None, value.encode(), 0x08000100))
                       for value in (service, account)]
            search = keep(self.cf.CFArrayCreate(None, (C.c_void_p * 1)(self.keychain), 1,
                                              self._callbacks("kCFTypeArrayCallBacks")))
            pairs = [("kSecClass", self._constant("kSecClassGenericPassword")),
                     ("kSecAttrService", strings[0]), ("kSecAttrAccount", strings[1]),
                     ("kSecMatchSearchList", search),
                     ("kSecAttrSynchronizable", self._constant("kCFBooleanFalse")),
                     ("kSecMatchLimit", self._constant("kSecMatchLimitOne")),
                     ("kSecReturnData", self._constant("kCFBooleanTrue")),
                     ("kSecUseAuthenticationUI", self._constant("kSecUseAuthenticationUIFail"))]
            keys = (C.c_void_p * len(pairs))(*(self._constant(key) for key, _ in pairs))
            values = (C.c_void_p * len(pairs))(*(value for _, value in pairs))
            query = keep(self.cf.CFDictionaryCreate(None, keys, values, len(pairs),
                self._callbacks("kCFTypeDictionaryKeyCallBacks"),
                self._callbacks("kCFTypeDictionaryValueCallBacks")))
            _check(self.sec.SecItemCopyMatching(query, C.byref(result)))
            if not result.value or self.cf.CFGetTypeID(result) != self.cf.CFDataGetTypeID():
                raise KeychainReadError("Keychain returned an invalid item type.")
            length = self.cf.CFDataGetLength(result)
            if not 1 <= length <= 4096:
                raise KeychainReadError("Keychain item size was rejected.")
            return C.string_at(self.cf.CFDataGetBytePtr(result), length).decode("utf-8")
        finally:
            if result.value:
                self.cf.CFRelease(result)
            for reference in reversed(owned):
                self.cf.CFRelease(reference)


def read_keychain_secrets(service):
    validate_service(service)
    payload = {}
    try:
        reader = _MacKeychain()
        with reader.session():
            for account in ACCOUNTS:
                payload[account] = reader.read(service, account)
        return validate_secrets(payload)
    except KeychainReadError:
        payload.clear()
        raise
    except Exception:
        payload.clear()
        raise KeychainReadError("Keychain values or access are invalid; no fallback was used.") from None
