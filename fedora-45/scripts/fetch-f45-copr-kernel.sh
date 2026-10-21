#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
set -Eeuo pipefail
set -x

usage()
{
	cat <<'EOF'
Usage: fetch-f45-copr-kernel.sh [--build BUILD_ID] OUTPUT_DIR

Download exactly the five binary RPMs pinned in ../files/sources.lock.json
for one COPR build. BUILD_ID defaults to 11035571, the first 7.2.8 update;
11177969 is the 7.3.0 fan-control upgrade, installed from a running 7.2.8.
"verify-f45-bundle.py builds" lists the pinned builds; others are refused.
OUTPUT_DIR and OUTPUT_DIR.partial must not exist; their parent must exist.
Failure removes only this invocation's partial directory. The source RPM is
provenance-only and is never downloaded.

SHA-256 and RPM metadata are checked against the selected build before
atomic publication of OUTPUT_DIR. The recorded packages reported NOKEY;
digest pins are not verified publisher signatures. This helper does not
install packages or contact a board.
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
build=11035571
if [[ ${1:-} == --build ]]; then
	[[ $# -ge 2 ]] || { usage >&2; exit 2; }
	build=$2
	shift 2
fi
[[ $# -eq 1 ]] || { usage >&2; exit 2; }
[[ $build =~ ^[1-9][0-9]{0,15}$ ]] ||
	fail "BUILD_ID must be a decimal COPR build ID."

for tool in basename curl dirname mkdir mv python3 realpath rm rpm; do
	command -v "$tool" >/dev/null ||
		fail "Required command not found: $tool"
done

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
verifier=$script_dir/verify-f45-bundle.py
test -f "$verifier" && test ! -L "$verifier" ||
	fail "Missing regular bundle verifier."
plan=$(python3 -I -B "$verifier" --build "$build" plan)

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
	python3 -I -B "$verifier" --build "$build" check-rpm "$partial/$filename"
done <<< "$plan"

python3 -I -B "$verifier" --build "$build" verify "$partial"
mv -nT -- "$partial" "$output_dir"
test ! -e "$partial" && test ! -L "$partial" ||
	fail "OUTPUT_DIR appeared during download; refusing to replace it."
trap - EXIT
printf 'Fetched the five pinned COPR build %s binary RPMs into %s\n' \
	"$build" "$output_dir"
