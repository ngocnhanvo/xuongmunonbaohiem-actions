#!/usr/bin/env python3
"""Read-only signed deploy path regression with a mock DirectAdmin-style host.

The fixture simulates PHP physical paths under /home/<user>/domains/, while
the signed GitHub Action sends FTP-visible /domains/<host>/public_html paths.
No external hosting or production credentials are contacted.
"""
import hashlib
import hmac
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

KEY = "testing-signed-unzip-key-long-enough-1234567890"


def signed_request(url, body):
    payload = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    signature = hmac.new(KEY.encode(), timestamp.encode() + b"\n" + payload, hashlib.sha256).hexdigest()
    req = Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "X-Esc-Deploy-Timestamp": timestamp,
        "X-Esc-Deploy-Signature": signature,
    }, method="POST")
    try:
        with urlopen(req, timeout=4) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        return exc.code, json.loads(exc.read())


def unsigned_request(url):
    try:
        with urlopen(url, timeout=4) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        return exc.code, json.loads(exc.read())


def main():
    with tempfile.TemporaryDirectory(prefix="esc-path-qa-") as tmp:
        domains = Path(tmp) / "home" / "hosting_account" / "domains"
        backend = domains / "admin.blue.test" / "public_html"
        frontend = domains / "blue.test" / "public_html"
        backend.mkdir(parents=True)
        frontend.mkdir(parents=True)
        shutil.copyfile("php-source/unzip.php", backend / "unzip.php")
        (backend / "wp-load.php").write_text(
            "<?php define('VCS_GH_ACTIONS_TOKEN', %s);\n" % json.dumps(KEY),
            encoding="utf-8",
        )
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        url = f"http://127.0.0.1:{port}/unzip.php"
        with open(Path(tmp) / "php-server.log", "wb") as log:
            server = subprocess.Popen(
                ["php", "-S", f"127.0.0.1:{port}", "-t", str(backend)],
                stdout=log, stderr=subprocess.STDOUT,
            )
            try:
                for _ in range(30):
                    try:
                        status, _ = unsigned_request(url)
                        if status == 405:
                            break
                    except (URLError, OSError):
                        time.sleep(0.1)
                else:
                    raise AssertionError("PHP fixture server never became ready")
                assert unsigned_request(url)[0] == 405, "GET must not trigger unzip"
                good = {
                    "action": "check", "host": "blue.test",
                    "target": "/domains/blue.test/public_html/",
                    "allow_override": False,
                }
                status, response = signed_request(url, good)
                assert status == 200, (status, response)
                assert response == {
                    "ok": True, "protocol": 2, "host": "blue.test",
                    "target": "/domains/blue.test/public_html/",
                }, response

                for changed, label in [
                    ({"target": "/domains/other.test/public_html/"}, "cross-site path"),
                    ({"target": "/domains/../blue.test/public_html/"}, "traversal"),
                    ({"target": "/domains/missing.test/public_html/",
                      "host": "missing.test"}, "missing frontend"),
                    ({"target": "/home/hosting_account/domains/blue.test/public_html/"}, "filesystem path injection"),
                ]:
                    status, response = signed_request(url, {**good, **changed})
                    assert status == 400 and response.get("ok") is False, (label, status, response)

                # An FTP domain directory which resolves through a symlink is also denied.
                alias = domains / "alias.test"
                alias.mkdir()
                (alias / "public_html").symlink_to(frontend, target_is_directory=True)
                status, response = signed_request(url, {
                    **good, "host": "alias.test",
                    "target": "/domains/alias.test/public_html/",
                })
                assert status == 400, ("symlink", status, response)
                print("PASS: virtual FTP path maps to hosting filesystem; signed check succeeds")
                print("PASS: GET, cross-domain, traversal, missing domain and symlink are rejected")
            finally:
                server.terminate()
                try:
                    server.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=4)


if __name__ == "__main__":
    main()
