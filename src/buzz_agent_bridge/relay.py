"""Authenticated read-only relay queries and signed receipts; no receive loop."""
import base64
import hashlib
import json
import time
import urllib.request
import uuid

from .crypto import verify_nostr


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError("Relay redirect refused")


class RelayReader:
    def __init__(self, config, signer, auth_tag):
        self.config, self.signer, self.auth_tag = config, signer, auth_tag
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)

    def query(self, filters):
        url = self.config["relay_url"] + "/query"
        body = json.dumps(filters, separators=(",", ":")).encode()
        event = self.signer({"kind": 27235, "created_at": int(time.time()), "content": "",
            "tags": [["u", url], ["method", "POST"], ["nonce", uuid.uuid4().hex],
                     ["payload", hashlib.sha256(body).hexdigest()]]})
        request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json",
            "Authorization": "Nostr " + base64.b64encode(json.dumps(event).encode()).decode(),
            "X-Auth-Tag": self.auth_tag})
        with self.opener.open(request, timeout=10) as response:
            data = response.read(1048577)
        if len(data) > 1048576:
            raise ValueError("Query too large")
        rows = json.loads(data)
        if not isinstance(rows, list) or any(not verify_nostr(row) for row in rows):
            raise ValueError("Query signature rejected")
        return rows

    def authorize(self, principal, channel):
        if principal != self.config["principal"] or channel != self.config["channel"]:
            return False
        try:
            rows = self.query([{"kinds": [39002], "#d": [channel], "limit": 2}])
            return (len(rows) == 1 and rows[0]["kind"] == 39002
                and [tag[1] for tag in rows[0]["tags"] if len(tag) > 1 and tag[0] == "d"] == [channel]
                and any(tag[:2] == ["p", self.signer.pubkey] for tag in rows[0]["tags"]))
        except Exception:
            return False

    def fetch(self, ident):
        return self.query([{"ids": [ident], "kinds": [9], "#h": [self.config["channel"]], "limit": 2}])
