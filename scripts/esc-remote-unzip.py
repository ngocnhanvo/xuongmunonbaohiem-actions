#!/usr/bin/env python3
"""Signed Astro ZIP deployment for Blue Sea. Uses existing GitHub Trigger PAT.

verify: read-only readiness + signed target check, before FTP upload.
unpack: verify artifact identity, then POST an authenticated unzip instruction.
"""
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request
from zipfile import ZipFile

READY = "ESC_ASTRO_UNZIP_PROTOCOL=2"
ORIGIN_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.-]*[a-z0-9]$")
TARGET_PATTERN = re.compile(r"^/domains/[A-Za-z0-9.-]+/public_html/$")


class RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Deploy endpoint unexpectedly redirected")


OPENER = build_opener(RejectRedirect)


def env_value(text, name):
    matches = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:].strip()
        if line.startswith(name + "="):
            value = line.split("=", 1)[1].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            matches.append(value)
    if len(matches) != 1 or not matches[0]:
        raise ValueError("Exactly one " + name + " must appear in ENV_FILE")
    return matches[0]


def validate_url(raw):
    parsed = urlsplit(raw)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.port not in (None, 443)
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ValueError("Expected an HTTPS origin URL without paths or query strings")
    host = parsed.hostname.lower()
    if not ORIGIN_PATTERN.fullmatch(host) or "." not in host or ".." in host:
        raise ValueError("Invalid domain name in ENV_FILE")
    return "https://" + parsed.netloc, host


def request(url, body=None, headers=None, timeout=20):
    method = "POST" if body is not None else "GET"
    req = Request(url, data=body, headers=headers or {}, method=method)
    try:
        with OPENER.open(req, timeout=timeout) as response:
            return response.read(8192).decode("utf-8")
    except HTTPError as exc:
        detail = exc.read(1000).decode("utf-8", "replace")
        raise RuntimeError("Unpack server returned HTTP %s: %s" % (exc.code, detail)) from exc
    except URLError as exc:
        raise RuntimeError("Cannot reach unzip endpoint: %s" % exc.reason) from exc


def signed_post(endpoint, token, data, timeout):
    raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    timestamp = str(int(time.time()))
    signature = hmac.new(token.encode("utf-8"), timestamp.encode("ascii") + b"\n" + raw, hashlib.sha256).hexdigest()
    response = request(
        endpoint,
        body=raw,
        headers={
            "Content-Type": "application/json",
            "X-Esc-Deploy-Timestamp": timestamp,
            "X-Esc-Deploy-Signature": signature,
        },
        timeout=timeout,
    )
    parsed = json.loads(response)
    if not isinstance(parsed, dict) or parsed.get("ok") is not True or parsed.get("protocol") != 2:
        raise RuntimeError("Server did not confirm signed unzip protocol v2")
    return parsed


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("verify", "unpack"):
        raise ValueError("Usage: esc-remote-unzip.py verify|unpack")
    mode = sys.argv[1]
    config = os.environ["ENV_FILE"]
    client_url = env_value(config, "WC_URL_CLIENT")
    admin_url = env_value(config, "WC_URL")
    _, client_host = validate_url(client_url)
    backend, _ = validate_url(admin_url)
    ftp_target = os.environ["ASTRO_FTP_TARGET"].strip()
    derived = "/domains/%s/public_html/" % client_host
    if not TARGET_PATTERN.fullmatch(ftp_target) or ".." in ftp_target or "//" in ftp_target:
        raise ValueError("FTP destination must be an explicit website public_html path")
    explicit_override = os.environ.get("FTP_ASTRO_DIR", "").strip()
    if ftp_target != derived and ftp_target != explicit_override:
        raise ValueError("FTP path differs from WC_URL_CLIENT without an explicit override")
    token = os.environ["SOURCE_REPO_PAT"]
    if len(token) < 20:
        raise ValueError("GitHub SOURCE_REPO_PAT is unavailable")
    common = {
        "host": client_host,
        "target": ftp_target,
        "allow_override": bool(explicit_override and ftp_target != derived),
    }

    if mode == "verify":
        marker = request(backend + "/unzip-v2.ready", timeout=12).strip()
        if marker != READY:
            raise RuntimeError("unzip-v2.ready is missing or incorrect; deploy the PHP endpoint first")
        result = signed_post(backend + "/unzip.php", token, {"action": "check", **common}, 30)
        if result.get("host") != client_host or result.get("target") != ftp_target:
            raise RuntimeError("Remote WordPress unzip target does not match the verified FTP target")
        print("SIGNED_UNZIP_PREFLIGHT_OK: %s" % ftp_target)
        return

    archive = Path(os.environ.get("ZIP_PATH", "source/upload/escvn.zip"))
    if not archive.is_file():
        raise ValueError("No Astro deployment ZIP exists")
    # Archived recovery ZIPs from a previous domain must not be deployed to a new domain.
    with ZipFile(archive) as zf:
        packaged_env = zf.read(".env").decode("utf-8")
        packaged_url = env_value(packaged_env, "WC_URL_CLIENT")
        if validate_url(packaged_url)[1] != client_host:
            raise ValueError("Archived ZIP was built for a different frontend domain")
        if "server/entry.mjs" not in zf.namelist():
            raise ValueError("Deployment ZIP is missing Astro server entry")
    sha = hashlib.sha256()
    with archive.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            sha.update(chunk)
    expected = sha.hexdigest()
    result = signed_post(backend + "/unzip.php", token, {
        "action": "unpack", **common, "sha256": expected,
    }, 180)
    if (result.get("host") != client_host or result.get("target") != ftp_target
            or result.get("sha256") != expected or result.get("files_activated", 0) < 2):
        raise RuntimeError("Unzip response did not match the uploaded deployment package")
    print("SIGNED_UNZIP_SUCCESS: target=%s files=%s" % (ftp_target, result["files_activated"]))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("::error::Signed unzip failed: %s" % exc, file=sys.stderr)
        sys.exit(1)
