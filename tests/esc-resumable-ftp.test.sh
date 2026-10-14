#!/usr/bin/env bash
# Offline contract checks: do not contact FTP or WordPress.
set -euo pipefail
cd "$(dirname "$0")/.."
bash -n scripts/esc-resumable-ftp.sh

temp="$(mktemp -d)"
trap 'rm -rf "$temp"' EXIT
mkdir -p "$temp/bin"
cat > "$temp/bin/lftp" <<'MOCK'
#!/usr/bin/env bash
cat > "$FTP_CAPTURE"
exit 0
MOCK
chmod +x "$temp/bin/lftp"
export PATH="$temp/bin:$PATH"
export FTP_SERVER=example.test FTP_USERNAME=test FTP_PASSWORD=fake
export ASTRO_FTP_TARGET=/domains/example.test/public_html/
export FTP_CAPTURE="$temp/ftp-commands.txt"
export GITHUB_STEP_SUMMARY="$temp/summary"
export ZIP_PATH="$temp/archive.zip"
printf 'Astro deployment artifact version A\n' > "$ZIP_PATH"
sha_a="$(sha256sum "$ZIP_PATH" | cut -d ' ' -f 1)"
bash scripts/esc-resumable-ftp.sh
grep -Fqx "put -c \"$ZIP_PATH\" -o \".escvn.${sha_a}.zip.uploading\"" "$FTP_CAPTURE"
if grep -Fq "rm -f .escvn.${sha_a}.zip.uploading" "$FTP_CAPTURE"; then
  echo 'Partial upload was deleted; resume would not work' >&2
  exit 1
fi
grep -Fqx 'set net:max-retries 3' "$FTP_CAPTURE"
grep -Fqx 'set net:timeout 25' "$FTP_CAPTURE"
grep -Fqx 'rm -f escvn.zip' "$FTP_CAPTURE"
grep -Fqx "mv \".escvn.${sha_a}.zip.uploading\" escvn.zip" "$FTP_CAPTURE"

# Same bytes across retry => exact same remote partial archive filename.
bash scripts/esc-resumable-ftp.sh
grep -Fqx "put -c \"$ZIP_PATH\" -o \".escvn.${sha_a}.zip.uploading\"" "$FTP_CAPTURE"

# Different bytes cannot accidentally resume the previous upload.
printf 'Astro deployment artifact version B\n' > "$ZIP_PATH"
sha_b="$(sha256sum "$ZIP_PATH" | cut -d ' ' -f 1)"
test "$sha_a" != "$sha_b"
bash scripts/esc-resumable-ftp.sh
grep -Fqx "put -c \"$ZIP_PATH\" -o \".escvn.${sha_b}.zip.uploading\"" "$FTP_CAPTURE"
if grep -Fq "$sha_a" "$FTP_CAPTURE"; then
  echo 'New ZIP still used an old SHA-named temp artifact' >&2
  exit 1
fi

# Reject untrusted target paths before contacting any FTP server.
if ASTRO_FTP_TARGET='/domains/example.test/../../public_html/' \
  bash scripts/esc-resumable-ftp.sh >/dev/null 2>&1; then
  echo 'Unsafe FTP path accepted' >&2
  exit 1
fi
if ZIP_PATH="$temp/missing.zip" bash scripts/esc-resumable-ftp.sh >/dev/null 2>&1; then
  echo 'Missing deployment package accepted' >&2
  exit 1
fi
grep -Fq 'approx' "$GITHUB_STEP_SUMMARY"
echo 'ESC_RESUMABLE_FTP_QA_PASS'
