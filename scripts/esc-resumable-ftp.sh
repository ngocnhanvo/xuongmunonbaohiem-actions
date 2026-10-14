#!/usr/bin/env bash
# Blue Sea Astro archive upload. SHA-256-specific remote names make put -c
# resumable across Actions jobs and network reconnects.
set -euo pipefail
: "${ZIP_PATH:?Set ZIP_PATH to an existing Astro ZIP}"
: "${ASTRO_FTP_TARGET:?Missing verified Astro FTP target}"
: "${FTP_SERVER:?Missing FTP_SERVER}"
: "${FTP_USERNAME:?Missing FTP_USERNAME}"
: "${FTP_PASSWORD:?Missing FTP_PASSWORD}"
test -s "$ZIP_PATH"

if [[ ! "$ASTRO_FTP_TARGET" =~ ^/[A-Za-z0-9._/-]+/$ ]] ||
   [[ "$ASTRO_FTP_TARGET" == *..* ]] ||
   [[ "$ASTRO_FTP_TARGET" == *'//'* ]]; then
  echo "::error::Invalid Astro FTP target" >&2
  exit 1
fi
local_sha="$(sha256sum "$ZIP_PATH" | cut -d ' ' -f 1)"
[[ "$local_sha" =~ ^[0-9a-f]{64}$ ]] || exit 1
local_size="$(stat -c %s "$ZIP_PATH")"
remote_temp=".escvn.${local_sha}.zip.uploading"
started=$SECONDS
echo "Starting Astro ZIP transfer: bytes=$local_size sha256=$local_sha"
echo "Remote temporary name is tied to ZIP checksum; existing partial upload can resume."

# Keep the incomplete remote ZIP for another attempt. The final unzip checks
# the full SHA-256, protecting against an incomplete or mismatched FTP upload.
set +e
timeout --signal=TERM --kill-after=10s 240s \
  lftp -u "$FTP_USERNAME","$FTP_PASSWORD" "ftp://$FTP_SERVER" <<LFTP
set cmd:fail-exit yes
set net:max-retries 3
set net:reconnect-interval-base 3
set net:timeout 25
set ftp:passive-mode yes
set ssl:verify-certificate no
set xfer:clobber yes
cd "$ASTRO_FTP_TARGET"
put -c "$ZIP_PATH" -o "$remote_temp"
rm -f escvn.zip
mv "$remote_temp" escvn.zip
bye
LFTP
status=$?
set -e
elapsed=$((SECONDS - started))
if (( status != 0 )); then
  echo "::error::FTP failed (exit=$status, duration=${elapsed}s); partial SHA-specific archive retained." >&2
  if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
    printf '%s\n' "- FTP failed after ${elapsed}s; partial archive retained (SHA prefix: ${local_sha:0:12})." >> "$GITHUB_STEP_SUMMARY"
  fi
  exit "$status"
fi
if (( elapsed > 0 )); then
  mib_sec="$(awk -v bytes="$local_size" -v secs="$elapsed" 'BEGIN {printf "%.2f", bytes / 1048576 / secs}')"
else
  mib_sec="n/a"
fi
echo "Resumable FTP complete in ${elapsed}s; ${local_size} bytes; approx ${mib_sec} MiB/s."
if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  printf '%s\n' "- FTP transfer: ${elapsed}s, ${local_size} bytes, approx ${mib_sec} MiB/s, SHA prefix ${local_sha:0:12}." >> "$GITHUB_STEP_SUMMARY"
fi
