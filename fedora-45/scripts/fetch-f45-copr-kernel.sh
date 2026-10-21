#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
set -Eeuo pipefail
set -x

usage()
{
	cat <<'EOF'
Usage: fetch-f45-copr-kernel.sh OUTPUT_DIR

Download exactly the five binary RPMs pinned in ../files/sources.lock.json
for COPR build 11035571. OUTPUT_DIR and OUTPUT_DIR.partial must not exist;
their parent must exist. Failure removes only this invocation's partial
directory. The source RPM is provenance-only and is never downloaded.

SHA-256 and RPM metadata are checked before atomic publication of OUTPUT_DIR.
The recorded packages reported NOKEY; digest pins are not verified publisher
signatures. This helper does not install packages or contact a board.
EOF
}

fail()
{
	printf 'error: %s\n' "$*" >&2
	exit 1
}

if [[ ${1:-} == -h || ${1:-} == --help ]]; then
	usage
	exit 0
fi
[[ $# -eq 1 ]] || { usage >&2; exit 2; }

for tool in basename curl dirname mkdir mv python3 realpath rm rpm; do
	command -v "$tool" >/dev/null ||
		fail "Required command not found: $tool"
done

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
verifier=$script_dir/verify-f45-bundle.py
test -f "$verifier" && test ! -L "$verifier" ||
	fail "Missing regular bundle verifier."
plan=$(python3 -I -B "$verifier" plan)

case "$1" in
''|*$'\n'*|*$'\r'*) fail "Unsafe or empty OUTPUT_DIR." ;;
esac
parent=$(realpath -e -- "$(dirname -- "$1")")
output_dir=$parent/$(basename -- "$1")
partial=$output_dir.partial
test ! -e "$output_dir" && test ! -L "$output_dir" ||
	fail "OUTPUT_DIR already exists."
test ! -e "$partial" && test ! -L "$partial" ||
	fail "Partial output already exists."

export LC_ALL=C
umask 077
mkdir -m 0700 -- "$partial"
cleanup()
{
	rm -rf -- "$partial"
}
trap cleanup EXIT

while IFS=$'\t' read -r expected_hash filename url; do
	[[ $expected_hash =~ ^[0-9a-f]{64}$ ]] ||
		fail "Invalid verifier output."
	curl \
		--fail --location --max-redirs 10 \
		--proto '=https' --proto-redir '=https' \
		--retry 3 --show-error \
		--output "$partial/$filename" "$url"
	python3 -I -B "$verifier" check-rpm "$partial/$filename"
done <<< "$plan"

python3 -I -B "$verifier" verify "$partial"
mv -nT -- "$partial" "$output_dir"
test ! -e "$partial" && test ! -L "$partial" ||
	fail "OUTPUT_DIR appeared during download; refusing to replace it."
trap - EXIT
printf 'Fetched the five pinned binary RPMs into %s\n' "$output_dir"
