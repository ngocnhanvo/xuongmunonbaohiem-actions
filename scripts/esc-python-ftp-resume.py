#!/usr/bin/env python3
"""Resume the existing Astro SHA-specific ZIP via FTP, reconnecting on stalls.

Used only by the artifact-recovery workflow. The signed remote unzip
independently validates the complete uploaded ZIP SHA-256 before extraction.
"""
from __future__ import annotations

import ftplib
import hashlib
import os
import pathlib
import re
import socket
import sys
import time

source = pathlib.Path(os.environ["ZIP_PATH"])
target = os.environ["ASTRO_FTP_TARGET"]
host = os.environ["FTP_SERVER"]
username = os.environ["FTP_USERNAME"]
password = os.environ["FTP_PASSWORD"]

if not source.is_file() or source.stat().st_size <= 0:
    raise SystemExit("Missing nonempty Astro ZIP")
if not re.fullmatch(r"/[A-Za-z0-9._/-]+/", target) or ".." in target or "//" in target:
    raise SystemExit("Unsafe remote FTP directory")
if os.getenv("FTP_PROTOCOL", "ftp") not in ("", "ftp"):
    raise SystemExit("This recovery script supports FTP only; refusing unexpected protocol")

digest = hashlib.sha256()
with source.open("rb") as stream:
    while piece := stream.read(1024 * 1024):
        digest.update(piece)
checksum = digest.hexdigest()
total_bytes = source.stat().st_size
temporary = f".escvn.{checksum}.zip.uploading"
filename = "escvn.zip"
maximum_attempts = 10

print(f"Python FTP recovery: bytes={total_bytes}, sha256={checksum}", flush=True)
print(f"Existing partial name: {temporary}", flush=True)

def remote_size(ftp: ftplib.FTP, name: str) -> int:
    ftp.voidcmd("TYPE I")
    try:
        size = ftp.size(name)
    except ftplib.error_perm as exc:
        if str(exc).startswith(("550", "450")):
            return 0
        raise
    return int(size or 0)

def connect() -> ftplib.FTP:
    ftp = ftplib.FTP(timeout=35)
    ftp.connect(host, 21, timeout=35)
    ftp.login(username, password)
    ftp.set_pasv(True)
    ftp.cwd(target)
    ftp.voidcmd("TYPE I")
    return ftp

for attempt in range(1, maximum_attempts + 1):
    ftp = None
    start = time.monotonic()
    try:
        ftp = connect()
        offset = remote_size(ftp, temporary)
        if offset > total_bytes:
            raise RuntimeError(f"Remote temporary ZIP larger than local archive: {offset}>{total_bytes}")
        print(f"FTP attempt {attempt}/{maximum_attempts}: offset={offset}/{total_bytes}", flush=True)

        if offset < total_bytes:
            transferred = offset
            next_update = offset + 5 * 1024 * 1024

            def report(chunk: bytes) -> None:
                global transferred, next_update
                transferred += len(chunk)
                if transferred >= next_update:
                    print(f"FTP progress {transferred}/{total_bytes} bytes", flush=True)
                    next_update = transferred + 5 * 1024 * 1024

            with source.open("rb") as stream:
                stream.seek(offset)
                ftp.storbinary(
                    "STOR " + temporary,
                    stream,
                    blocksize=128 * 1024,
                    callback=report,
                    rest=offset if offset else None,
                )

        actual = remote_size(ftp, temporary)
        if actual != total_bytes:
            raise RuntimeError(f"FTP temporary ZIP size mismatch: {actual}/{total_bytes}")

        try:
            ftp.delete(filename)
        except ftplib.error_perm as exc:
            if not str(exc).startswith(("550", "450")):
                raise
        ftp.rename(temporary, filename)
        final_size = remote_size(ftp, filename)
        if final_size != total_bytes:
            raise RuntimeError(f"Final ZIP size mismatch: {final_size}/{total_bytes}")

        duration = round(time.monotonic() - start, 1)
        print(f"Python FTP recovery complete: {total_bytes} bytes, attempt={attempt}, elapsed={duration}s", flush=True)
        if os.getenv("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
                summary.write(f"- Python FTP resume success: {total_bytes} bytes; SHA prefix {checksum[:12]}; attempt {attempt}.\\n")
        try:
            ftp.quit()
        except ftplib.all_errors:
            pass
        sys.exit(0)
    except (OSError, TimeoutError, socket.timeout, ftplib.Error, RuntimeError, EOFError) as error:
        print(f"FTP attempt {attempt} interrupted after {round(time.monotonic()-start,1)}s: {type(error).__name__}: {error}", flush=True)
        if attempt == maximum_attempts:
            raise SystemExit("FTP archive transfer failed after all reconnect attempts") from error
        time.sleep(min(3 * attempt, 15))
    finally:
        if ftp:
            try:
                ftp.close()
            except Exception:
                pass
