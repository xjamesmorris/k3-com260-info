#!/usr/bin/env bash
set -Eeuo pipefail
set -x

LC_ALL=C
export LC_ALL
unset CDPATH
umask 077

usage()
{
	cat <<'EOF'
Usage: k3-run-fedora-guest.sh ACTION GUEST_DIR [QEMU_BIN]

Manage a persistent Fedora riscv64 KVM guest staged in GUEST_DIR.

Actions:
  run
    Verify the stage and launch QEMU in the foreground with an interactive
    serial console. The mutable overlay.qcow2 is used persistently.
  resume
    Safely boot the same persistent overlay.qcow2 again. This is not QEMU
    snapshot resume and never uses an internal or temporary QEMU snapshot.
  status
    Report whether the recorded guest PID is active and identity-matched.
    This reporting action never cleans or otherwise changes runtime state.
  stop
    Request exactly "sudo -n systemctl poweroff" over BatchMode localhost SSH
    as the manifested guest user, then wait a bounded interval for QEMU exit.
  terminate
    For a guest that never reaches SSH, send one identity-checked SIGTERM to
    the recorded numeric QEMU PID. This requires an explicit per-run
    acknowledgment and is not an in-guest filesystem shutdown.

QEMU_BIN is accepted only by run and resume and defaults to
qemu-system-riscv64.

GUEST_DIR may be relative, but its resolved absolute path may contain only
ASCII letters, digits, "_", ".", "/", "+", and "-".

Environment:
  K3_FEDORA_CPU
    QEMU CPU model and properties (default: host).
  K3_FEDORA_VCPUS
    Virtual CPUs, from 1 through 8 (default: 4).
  K3_FEDORA_MEMORY
    Positive integral QEMU size token, optionally suffixed K through E
    (default: 4G).
  K3_FEDORA_SSH_PORT
    Unprivileged localhost TCP port, 1024 through 65535 (default: 2222).
  K3_FEDORA_SSH_IDENTITY
    Optional readable regular private-key file for stop. When set, SSH uses
    only this identity; when unset, SSH uses ssh-agent/default identities.
  K3_FEDORA_AIA
    Interrupt-controller mode: plic or aplic-imsic (default: plic).
  K3_FEDORA_STOP_TIMEOUT
    Seconds to wait for QEMU to exit after the SSH poweroff request, from
    1 through 3600 (default: 60).
  K3_FEDORA_TERMINATE_TIMEOUT
    Seconds to wait after SIGTERM, from 1 through 3600 (default: 30).
  K3_FEDORA_ACK_UNCLEAN_TERMINATION
    Must be exactly YES for every terminate invocation.
  K3_FEDORA_EXTRA_APPEND
    Optional single-line extra kernel command-line text. CR and LF are
    rejected, and the complete kernel command line is passed as one -append
    argument.

Kernel command line:
  Every run and resume uses the staged BLS options from boot/cmdline.txt,
  appends console=ttyS0,115200n8, then appends K3_FEDORA_EXTRA_APPEND when
  that optional text is non-empty.

Required GUEST_DIR layout:
  base.img
  base-format.txt
  overlay.qcow2
  seed.img
  user-data
  meta-data
  boot/vmlinuz
  boot/initramfs.img
  boot/cmdline.txt
  source.txt
  SHA256SUMS

SHA256SUMS must contain exactly the nine immutable files above other than
overlay.qcow2 and SHA256SUMS itself. Runtime PID, QMP, lock, and owner-only
SSH known-hosts files are kept under GUEST_DIR/.runtime/.

Normal login:
  ssh -p PORT USER@127.0.0.1

Use the exact "Guest user: USER" value from the manifested source.txt.
Use stop for a clean in-guest shutdown. terminate closes QEMU and its block
backends but does not shut down the guest filesystem and may require guest
filesystem recovery.
EOF
}

fail()
{
	printf 'error: %s\n' "$*" >&2
	exit 1
}

usage_error()
{
	printf 'error: %s\n\n' "$*" >&2
	usage >&2
	exit 2
}

require_command()
{
	command -v "$1" >/dev/null ||
		fail "required command not found: $1"
}

reject_line_breaks()
{
	local label=$1
	local value=$2

	case "$value" in
	*$'\n'*|*$'\r'*)
		fail "$label must not contain CR or LF."
		;;
	esac
}

assert_owned_path()
{
	local path=$1
	local label=$2
	local owner

	owner=$(stat -Lc '%u' -- "$path") ||
		fail "cannot inspect $label ownership: $path"
	if [[ $owner -ne $EUID ]]; then
		fail "$label is not owned by the current user: $path"
	fi
}

assert_not_group_or_other_writable()
{
	local path=$1
	local label=$2
	local permissions

	permissions=$(stat -Lc '%A' -- "$path") ||
		fail "cannot inspect $label permissions: $path"
	if [[ ${permissions:5:1} == w || ${permissions:8:1} == w ]]; then
		fail "$label must not be group- or other-writable: $path"
	fi
}

assert_owner_only()
{
	local path=$1
	local label=$2
	local permissions

	permissions=$(stat -Lc '%a' -- "$path") ||
		fail "cannot inspect $label permissions: $path"
	if (((8#$permissions & 077) != 0)); then
		fail "$label must not grant group or other permissions: $path"
	fi
}

assert_trusted_directory()
{
	local path=$1
	local label=$2

	if [[ -L $path || ! -d $path ]]; then
		fail "$label must be a real directory, not a symlink: $path"
	fi
	assert_owned_path "$path" "$label"
	assert_not_group_or_other_writable "$path" "$label"
}

resolve_guest_dir()
{
	local input=$1

	reject_line_breaks GUEST_DIR "$input"
	case "$input" in
	''|*,*)
		fail "GUEST_DIR must be non-empty and must not contain a comma."
		;;
	esac
	while [[ $input != / && $input == */ ]]; do
		input=${input%/}
	done
	if [[ -L $input || ! -d $input ]]; then
		fail "GUEST_DIR must be an existing real directory: $input"
	fi
	guest_dir=$(cd -- "$input" && pwd -P) ||
		fail "cannot resolve GUEST_DIR: $input"
	if [[ ! $guest_dir =~ ^/[A-Za-z0-9_./+-]*$ ]]; then
		fail "resolved GUEST_DIR may contain only ASCII letters, digits, '_', '.', '/', '+', and '-': $guest_dir"
	fi
	assert_trusted_directory "$guest_dir" GUEST_DIR

	runtime_dir=$guest_dir/.runtime
	pid_file=$runtime_dir/qemu.pid
	qmp_socket=$runtime_dir/qmp.sock
	lock_file=$runtime_dir/launch.lock
	known_hosts_file=$runtime_dir/known_hosts
	overlay=$guest_dir/overlay.qcow2
	base_image=$guest_dir/base.img
	seed_image=$guest_dir/seed.img

	if ! "$python_bin" - "$qmp_socket" <<'PY'
import os
import sys

path = os.fsencode(sys.argv[1])
if len(path) > 107:
    raise SystemExit(1)
PY
	then
		fail "QMP Unix socket path exceeds the 107-byte Linux limit: $qmp_socket"
	fi
}

validate_runtime_entry()
{
	local path=$1
	local kind=$2

	if [[ ! -e $path && ! -L $path ]]; then
		return
	fi
	if [[ -L $path ]]; then
		fail "refusing symlink runtime $kind: $path"
	fi
	case "$kind" in
	PID|lock)
		[[ -f $path ]] ||
			fail "runtime $kind path is not a regular file: $path"
		;;
	known-hosts)
		[[ -f $path && -r $path && -w $path ]] ||
			fail "runtime $kind path must be a readable, writable regular file: $path"
		;;
	QMP)
		[[ -S $path ]] ||
			fail "runtime QMP path is not a Unix socket: $path"
		;;
	*)
		fail "internal error: unknown runtime entry kind: $kind"
		;;
	esac
	assert_owned_path "$path" "runtime $kind path"
	if [[ $kind == known-hosts ]]; then
		assert_owner_only "$path" "runtime $kind path"
	else
		assert_not_group_or_other_writable "$path" "runtime $kind path"
	fi
}

validate_runtime_dir()
{
	assert_trusted_directory "$runtime_dir" "runtime directory"
	validate_runtime_entry "$pid_file" PID
	validate_runtime_entry "$qmp_socket" QMP
	validate_runtime_entry "$lock_file" lock
	validate_runtime_entry "$known_hosts_file" known-hosts
}

ensure_runtime_dir()
{
	if [[ ! -e $runtime_dir && ! -L $runtime_dir ]]; then
		mkdir -- "$runtime_dir" ||
			fail "cannot create runtime directory: $runtime_dir"
	fi
	validate_runtime_dir
}

ensure_known_hosts_file()
{
	if ! "$python_bin" - "$known_hosts_file" <<'PY'
import os
import stat
import sys

path = sys.argv[1]
flags = os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_CLOEXEC | os.O_NOFOLLOW
try:
    descriptor = os.open(path, flags, 0o600)
except OSError as exc:
    print(f"cannot securely open SSH known-hosts file {path}: {exc}",
          file=sys.stderr)
    raise SystemExit(1)
try:
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError("path is not a regular file")
    if metadata.st_uid != os.geteuid():
        raise RuntimeError(
            f"path belongs to UID {metadata.st_uid}, not UID {os.geteuid()}"
        )
    if metadata.st_mode & 0o077:
        raise RuntimeError("path grants group or other permissions")
    if not os.access(path, os.R_OK | os.W_OK, follow_symlinks=False):
        raise RuntimeError("path is not readable and writable")
except RuntimeError as exc:
    print(f"unsafe SSH known-hosts file {path}: {exc}", file=sys.stderr)
    raise SystemExit(1)
finally:
    os.close(descriptor)
PY
	then
		fail "cannot create or validate owner-only SSH known-hosts file: $known_hosts_file"
	fi
	validate_runtime_entry "$known_hosts_file" known-hosts
}

read_recorded_pid()
{
	local value

	if ! value=$(
		"$python_bin" - "$pid_file" <<'PY'
import re
import sys

path = sys.argv[1]
try:
    data = open(path, "rb").read(65)
except OSError as exc:
    print(f"cannot read PID file {path}: {exc}", file=sys.stderr)
    raise SystemExit(1)
if len(data) > 64:
    print(f"oversized PID file: {path}", file=sys.stderr)
    raise SystemExit(1)
if not re.fullmatch(rb"[1-9][0-9]*\n?", data):
    print(f"malformed PID file: {path}", file=sys.stderr)
    raise SystemExit(1)
pid = int(data.strip())
if pid > 2147483647:
    print(f"out-of-range PID in {path}", file=sys.stderr)
    raise SystemExit(1)
print(pid)
PY
	); then
		return 1
	fi
	recorded_pid=$value
}

argv_has_pair()
{
	local wanted_option=$1
	local wanted_value=$2
	shift 2
	local -a values=("$@")
	local index

	for ((index = 0; index + 1 < ${#values[@]}; index++)); do
		if [[ ${values[index]} == "$wanted_option" &&
		      ${values[index + 1]} == "$wanted_value" ]]; then
			return 0
		fi
	done
	return 1
}

pid_identity_matches()
{
	local pid=$1
	local proc_dir=/proc/$pid
	local owner
	local proc_state
	local -a proc_argv=()

	pid_identity_detail=
	if [[ ! -d $proc_dir ]]; then
		pid_identity_detail="PID $pid is not active."
		return 1
	fi
	if ! owner=$(stat -Lc '%u' -- "$proc_dir"); then
		if [[ ! -d $proc_dir ]]; then
			pid_identity_detail="PID $pid exited during identity validation."
			return 1
		fi
		pid_identity_detail="cannot inspect ownership for live PID $pid."
		return 3
	fi
	if [[ $owner -ne $EUID ]]; then
		pid_identity_detail="live PID $pid belongs to UID $owner, not UID $EUID."
		return 2
	fi
	if ! proc_state=$(
		"$python_bin" - "$proc_dir/stat" <<'PY'
import sys

path = sys.argv[1]
try:
    data = open(path, "rb").read(8193)
except OSError as exc:
    print(f"cannot read process state from {path}: {exc}", file=sys.stderr)
    raise SystemExit(1)
if len(data) > 8192:
    print(f"oversized process state file: {path}", file=sys.stderr)
    raise SystemExit(1)
closing = data.rfind(b") ")
if closing < 0:
    print(f"malformed process state file: {path}", file=sys.stderr)
    raise SystemExit(1)
fields = data[closing + 2:].split()
if not fields or fields[0] not in b"RSDZTWtXxIKP":
    print(f"invalid process state in {path}", file=sys.stderr)
    raise SystemExit(1)
sys.stdout.buffer.write(fields[0])
PY
	); then
		if [[ ! -d $proc_dir ]]; then
			pid_identity_detail="PID $pid exited during state validation."
			return 1
		fi
		pid_identity_detail="cannot read a safe process state for live PID $pid."
		return 3
	fi
	if [[ $proc_state == Z || $proc_state == X || $proc_state == x ]]; then
		pid_identity_detail="PID $pid has exited and is awaiting process reaping."
		return 1
	fi
	if ! mapfile -d '' -t proc_argv < "$proc_dir/cmdline"; then
		if [[ ! -d $proc_dir ]]; then
			pid_identity_detail="PID $pid exited during command-line validation."
			return 1
		fi
		pid_identity_detail="cannot read /proc/$pid/cmdline."
		return 3
	fi
	if [[ ${#proc_argv[@]} -eq 0 ]]; then
		if [[ ! -d $proc_dir ]]; then
			pid_identity_detail="PID $pid exited during command-line validation."
			return 1
		fi
		pid_identity_detail="live PID $pid has no safely readable command line."
		return 3
	fi
	if ! argv_has_pair \
		-pidfile "$pid_file" "${proc_argv[@]}"; then
		pid_identity_detail="live PID $pid lacks the exact guest PID-file argument."
		return 2
	fi
	if ! argv_has_pair \
		-qmp "unix:$qmp_socket,server=on,wait=off" "${proc_argv[@]}"; then
		pid_identity_detail="live PID $pid lacks the exact guest QMP argument."
		return 2
	fi
	if ! argv_has_pair \
		-drive "file=$overlay,format=qcow2,if=none,id=root" \
		"${proc_argv[@]}"; then
		pid_identity_detail="live PID $pid does not reference the exact overlay path."
		return 2
	fi
	if ! argv_has_pair \
		-drive "file=$seed_image,format=raw,if=none,id=seed,readonly=on" \
		"${proc_argv[@]}"; then
		pid_identity_detail="live PID $pid does not reference the exact seed path."
		return 2
	fi
	if ! argv_has_pair \
		-kernel "$guest_dir/boot/vmlinuz" "${proc_argv[@]}"; then
		pid_identity_detail="live PID $pid does not reference the exact kernel path."
		return 2
	fi
	if ! argv_has_pair \
		-initrd "$guest_dir/boot/initramfs.img" "${proc_argv[@]}"; then
		pid_identity_detail="live PID $pid does not reference the exact initramfs path."
		return 2
	fi
	return 0
}

scan_for_matching_process()
{
	local output
	local -a matches=()

	scanned_pid=
	if ! output=$(
		"$python_bin" - \
			"$EUID" \
			"$pid_file" \
			"unix:$qmp_socket,server=on,wait=off" \
			"file=$overlay,format=qcow2,if=none,id=root" \
			"file=$seed_image,format=raw,if=none,id=seed,readonly=on" \
			"$guest_dir/boot/vmlinuz" \
			"$guest_dir/boot/initramfs.img" <<'PY'
import os
import sys

uid = int(sys.argv[1])
expected_pairs = [
    (b"-pidfile", os.fsencode(sys.argv[2])),
    (b"-qmp", os.fsencode(sys.argv[3])),
    (b"-drive", os.fsencode(sys.argv[4])),
    (b"-drive", os.fsencode(sys.argv[5])),
    (b"-kernel", os.fsencode(sys.argv[6])),
    (b"-initrd", os.fsencode(sys.argv[7])),
]
matches = []
uncertain = []

for name in os.listdir("/proc"):
    if not name.isdigit():
        continue
    proc_dir = os.path.join("/proc", name)
    try:
        if os.stat(proc_dir).st_uid != uid:
            continue
    except FileNotFoundError:
        continue
    except OSError as exc:
        uncertain.append(f"{name}: stat failed: {exc}")
        continue
    try:
        with open(os.path.join(proc_dir, "cmdline"), "rb") as stream:
            data = stream.read()
    except FileNotFoundError:
        continue
    except OSError as exc:
        if not os.path.exists(proc_dir):
            continue
        uncertain.append(f"{name}: cmdline read failed: {exc}")
        continue
    if not data:
        continue
    argv = data.rstrip(b"\0").split(b"\0")
    if all(
        any(
            argv[index] == option and argv[index + 1] == value
            for index in range(len(argv) - 1)
        )
        for option, value in expected_pairs
    ):
        matches.append(int(name))

if uncertain:
    print(
        "cannot safely complete process identity scan: " + "; ".join(uncertain),
        file=sys.stderr,
    )
    raise SystemExit(1)
for pid in sorted(matches):
    print(pid)
PY
	); then
		runtime_detail="cannot safely scan current-user processes for this guest."
		return 2
	fi
	if [[ -n $output ]]; then
		mapfile -t matches <<< "$output"
	fi
	case "${#matches[@]}" in
	0)
		return 1
		;;
	1)
		scanned_pid=${matches[0]}
		return 0
		;;
	*)
		runtime_detail="multiple processes match this guest: ${matches[*]}"
		return 2
		;;
	esac
}

classify_runtime()
{
	local identity_status
	local scan_status

	runtime_state=inactive
	runtime_detail=
	runtime_pid=
	recorded_pid=

	if [[ ! -e $runtime_dir && ! -L $runtime_dir ]]; then
		if scan_for_matching_process; then
			runtime_state=orphan-active
			runtime_pid=$scanned_pid
			runtime_detail="PID $scanned_pid matches the guest, but the runtime directory is missing."
		else
			scan_status=$?
			if [[ $scan_status -eq 2 ]]; then
				runtime_state=unverifiable
			else
				runtime_detail="runtime directory does not exist."
			fi
		fi
		return
	fi
	validate_runtime_dir

	if [[ -e $pid_file ]]; then
		if ! read_recorded_pid; then
			runtime_state=unverifiable
			runtime_detail="the recorded PID is malformed or unreadable."
			return
		fi
		if pid_identity_matches "$recorded_pid"; then
			runtime_state=active
			runtime_pid=$recorded_pid
			runtime_detail="recorded PID is active and identity-matched."
			return
		else
			identity_status=$?
		fi
		case "$identity_status" in
		1)
			if scan_for_matching_process; then
				runtime_state=orphan-active
				runtime_pid=$scanned_pid
				runtime_detail="PID file is stale, but PID $scanned_pid matches the guest."
			else
				scan_status=$?
				if [[ $scan_status -eq 1 ]]; then
					runtime_state=stale
					runtime_detail="recorded PID is absent and no matching guest is active."
				else
					runtime_state=unverifiable
				fi
			fi
			;;
		2)
			runtime_state=identity-mismatch
			runtime_pid=$recorded_pid
			runtime_detail=$pid_identity_detail
			;;
		3)
			runtime_state=unverifiable
			runtime_pid=$recorded_pid
			runtime_detail=$pid_identity_detail
			;;
		*)
			fail "internal error: unexpected PID identity status: $identity_status"
			;;
		esac
		return
	fi

	if scan_for_matching_process; then
		runtime_state=orphan-active
		runtime_pid=$scanned_pid
		runtime_detail="PID $scanned_pid matches the guest, but the PID file is missing."
	else
		scan_status=$?
		if [[ $scan_status -eq 2 ]]; then
			runtime_state=unverifiable
		elif [[ -e $qmp_socket ]]; then
			runtime_state=stale
			runtime_detail="QMP socket is stale and no matching guest is active."
		else
			runtime_state=inactive
			runtime_detail="no recorded or matching guest process is active."
		fi
	fi
}

cleanup_stale_runtime()
{
	local cleanup_lock_fd
	local temporary_lock=0
	local scan_status

	if [[ ${launch_lock_held:-0} -ne 1 ]]; then
		exec {cleanup_lock_fd}>>"$lock_file"
		if ! flock -n "$cleanup_lock_fd"; then
			exec {cleanup_lock_fd}>&-
			runtime_detail="launch lock is busy; stale runtime cleanup was not attempted."
			return 1
		fi
		temporary_lock=1
	fi
	if scan_for_matching_process; then
		runtime_detail="PID $scanned_pid now matches the guest; stale cleanup was refused."
		if [[ $temporary_lock -eq 1 ]]; then
			exec {cleanup_lock_fd}>&-
		fi
		return 1
	else
		scan_status=$?
		if [[ $scan_status -ne 1 ]]; then
			if [[ $temporary_lock -eq 1 ]]; then
				exec {cleanup_lock_fd}>&-
			fi
			return 1
		fi
	fi
	validate_runtime_entry "$pid_file" PID
	validate_runtime_entry "$qmp_socket" QMP
	rm -f -- "$pid_file" "$qmp_socket"
	if [[ $temporary_lock -eq 1 ]]; then
		exec {cleanup_lock_fd}>&-
	fi
}

read_ascii_single_line()
{
	local path=$1
	local label=$2
	local output_variable=$3
	local value

	if ! value=$(
		"$python_bin" - "$path" "$label" <<'PY'
import sys

path, label = sys.argv[1:3]
try:
    data = open(path, "rb").read(65537)
except OSError as exc:
    print(f"cannot read {label} {path}: {exc}", file=sys.stderr)
    raise SystemExit(1)
if len(data) > 65536:
    print(f"{label} is too large: {path}", file=sys.stderr)
    raise SystemExit(1)
if data.endswith(b"\n"):
    data = data[:-1]
if not data or b"\n" in data or b"\r" in data or b"\0" in data:
    print(f"{label} must contain exactly one non-empty line: {path}", file=sys.stderr)
    raise SystemExit(1)
try:
    text = data.decode("ascii")
except UnicodeDecodeError:
    print(f"{label} must contain ASCII text: {path}", file=sys.stderr)
    raise SystemExit(1)
if any(ord(char) < 0x20 or ord(char) > 0x7e for char in text):
    print(f"{label} contains non-printable text: {path}", file=sys.stderr)
    raise SystemExit(1)
sys.stdout.write(text)
PY
	); then
		fail "invalid $label: $path"
	fi
	printf -v "$output_variable" '%s' "$value"
}

validate_manifest()
{
	local manifest=$guest_dir/SHA256SUMS
	local -a immutable_paths=(
		base.img
		base-format.txt
		seed.img
		user-data
		meta-data
		boot/vmlinuz
		boot/initramfs.img
		boot/cmdline.txt
		source.txt
	)

	if ! "$python_bin" - "$manifest" "${immutable_paths[@]}" <<'PY'
import re
import sys

manifest = sys.argv[1]
expected = set(sys.argv[2:])
try:
    data = open(manifest, "rb").read(65537)
except OSError as exc:
    print(f"cannot read manifest {manifest}: {exc}", file=sys.stderr)
    raise SystemExit(1)
if len(data) > 65536 or not data.endswith(b"\n"):
    print(f"manifest must be non-empty, bounded, and newline-terminated: {manifest}",
          file=sys.stderr)
    raise SystemExit(1)
if b"\r" in data or b"\0" in data:
    print(f"manifest contains a forbidden CR or NUL byte: {manifest}",
          file=sys.stderr)
    raise SystemExit(1)
lines = data[:-1].split(b"\n")
entry = re.compile(rb"^([0-9A-Fa-f]{64}) ([ *])(.+)$")
seen = set()
for line in lines:
    match = entry.fullmatch(line)
    if not match:
        print(f"malformed manifest entry: {line!r}", file=sys.stderr)
        raise SystemExit(1)
    try:
        path = match.group(3).decode("ascii")
    except UnicodeDecodeError:
        print("manifest path is not ASCII", file=sys.stderr)
        raise SystemExit(1)
    if path not in expected or path in seen:
        print(f"unexpected or duplicate manifest path: {path}", file=sys.stderr)
        raise SystemExit(1)
    seen.add(path)
if seen != expected or len(lines) != len(expected):
    missing = sorted(expected - seen)
    extra = sorted(seen - expected)
    print(f"manifest path set mismatch; missing={missing}, extra={extra}",
          file=sys.stderr)
    raise SystemExit(1)
PY
	then
		fail "SHA256SUMS is malformed or does not describe the exact immutable stage."
	fi
	(
		cd -- "$guest_dir"
		sha256sum --check --strict --status SHA256SUMS
	) || fail "immutable stage checksum verification failed: $manifest"
}

preflight_qcow2_header()
{
	local role=$1
	local path=$2

	# Inspect path-bearing qcow2 fields before qemu-img can follow them.
	"$python_bin" - "$role" "$path" <<'PY'
import os
import struct
import sys

role, path = sys.argv[1:3]
if role not in {"base", "overlay"}:
    raise SystemExit(f"unknown qcow2 preflight role: {role}")

try:
    with open(path, "rb") as image:
        file_size = os.fstat(image.fileno()).st_size
        header = image.read(104)

        magic_matches = header[:4] == b"QFI\xfb"
        if not magic_matches:
            if role == "base":
                print("raw")
                raise SystemExit(0)
            raise SystemExit("overlay does not have a valid qcow2 magic")
        if len(header) < 8:
            raise SystemExit("truncated qcow2 version field")
        version = struct.unpack(">I", header[4:8])[0]
        if version not in {2, 3}:
            raise SystemExit(f"unsupported qcow2 version: {version}")

        minimum_header_size = 72 if version == 2 else 104
        if len(header) < minimum_header_size:
            raise SystemExit("truncated qcow2 header")

        backing_offset = struct.unpack(">Q", header[8:16])[0]
        backing_size = struct.unpack(">I", header[16:20])[0]
        cluster_bits = struct.unpack(">I", header[20:24])[0]
        if not 9 <= cluster_bits <= 21:
            raise SystemExit(f"unsupported qcow2 cluster bits: {cluster_bits}")
        cluster_size = 1 << cluster_bits

        if version == 2:
            header_length = 72
            incompatible_features = 0
        else:
            incompatible_features = struct.unpack(">Q", header[72:80])[0]
            header_length = struct.unpack(">I", header[100:104])[0]
            if header_length < 104 or header_length % 8:
                raise SystemExit(f"invalid qcow2 header length: {header_length}")
        if header_length > cluster_size or header_length > file_size:
            raise SystemExit("qcow2 header length extends beyond the image header")

        if incompatible_features & (1 << 2):
            raise SystemExit(f"{role} qcow2 image uses an external data file")

        if role == "base":
            if backing_offset != 0 or backing_size != 0:
                raise SystemExit("base qcow2 image has a backing filename")
            print("qcow2")
            raise SystemExit(0)

        if backing_size > 1023:
            raise SystemExit("overlay backing filename exceeds the qcow2 limit")
        backing_end = backing_offset + backing_size
        if (
            backing_offset < header_length
            or backing_end > cluster_size
            or backing_end > file_size
        ):
            raise SystemExit("overlay backing filename is outside the bounded image header")
        image.seek(backing_offset)
        backing = image.read(backing_size)
except OSError as exc:
    raise SystemExit(f"cannot preflight {path}: {exc}")

if backing != b"base.img":
    raise SystemExit("overlay backing filename must be the literal ASCII base.img")
PY
}

validate_storage()
{
	local declared_base_format
	local detected_base_format
	local base_info
	local overlay_info

	read_ascii_single_line \
		"$guest_dir/base-format.txt" "base image format" declared_base_format
	case "$declared_base_format" in
	raw|qcow2)
		;;
	*)
		fail "base-format.txt must contain exactly raw or qcow2: $declared_base_format"
		;;
	esac
	if ! detected_base_format=$(
		preflight_qcow2_header base "$base_image"
	); then
		fail "base image header preflight failed: $base_image"
	fi
	if [[ $detected_base_format != "$declared_base_format" ]]; then
		fail "base-format.txt declares $declared_base_format, but base.img is $detected_base_format"
	fi
	if ! preflight_qcow2_header overlay "$overlay"; then
		fail "persistent overlay header preflight failed: $overlay"
	fi

	if ! base_info=$(
		"$qemu_img_bin" info \
			-f "$detected_base_format" --output=json "$base_image"
	); then
		fail "qemu-img could not inspect the base image: $base_image"
	fi
	if ! overlay_info=$(
		"$qemu_img_bin" info -f qcow2 --output=json "$overlay"
	); then
		fail "qemu-img could not inspect the persistent overlay: $overlay"
	fi
	if ! "$python_bin" - \
		"$overlay" "$base_image" "$detected_base_format" \
		"$base_info" "$overlay_info" <<'PY'
import json
import os
import sys

overlay, base, expected_base_format, base_json, overlay_json = sys.argv[1:6]

def parse_info(label, value):
    try:
        info = json.loads(value)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid qemu-img JSON for {label}: {exc}")
    if not isinstance(info, dict):
        raise SystemExit(f"qemu-img JSON for {label} is not an object")
    return info

def reject_external_data(label, value):
    if isinstance(value, dict):
        if value.get("name") == "data-file":
            raise SystemExit(f"{label} exposes an external data-file child")
        for key, child in value.items():
            if (
                key in {"data-file", "full-data-file"}
                and child is not None
                and child != ""
            ):
                raise SystemExit(f"{label} has external {key} metadata")
            reject_external_data(label, child)
    elif isinstance(value, list):
        for child in value:
            reject_external_data(label, child)

base_info = parse_info("base image", base_json)
info = parse_info("overlay", overlay_json)
if base_info.get("format") != expected_base_format:
    raise SystemExit(
        f"base image format is {base_info.get('format')!r}, "
        f"expected {expected_base_format!r}"
    )
for key in ("backing-filename", "full-backing-filename"):
    if base_info.get(key) not in {None, ""}:
        raise SystemExit(f"base image has unexpected {key} metadata")
reject_external_data("base image", base_info)

if info.get("format") != "qcow2":
    print("overlay format is not qcow2", file=sys.stderr)
    raise SystemExit(1)
backing = info.get("backing-filename")
if backing != "base.img":
    print("overlay backing filename is not the literal base.img", file=sys.stderr)
    raise SystemExit(1)
if os.path.isabs(backing):
    resolved_backing = os.path.realpath(backing)
else:
    resolved_backing = os.path.realpath(
        os.path.join(os.path.dirname(overlay), backing)
    )
expected_base = os.path.realpath(base)
if resolved_backing != expected_base:
    print(
        f"overlay backing resolves to {resolved_backing}, expected {expected_base}",
        file=sys.stderr,
    )
    raise SystemExit(1)
full_backing = info.get("full-backing-filename")
if full_backing is not None:
    if not isinstance(full_backing, str) or os.path.realpath(full_backing) != expected_base:
        print("qemu-img full backing filename does not match base.img",
              file=sys.stderr)
        raise SystemExit(1)
actual_backing_format = info.get("backing-filename-format")
if actual_backing_format != expected_base_format:
    print(
        f"overlay backing format is {actual_backing_format!r}, "
        f"expected {expected_base_format!r}",
        file=sys.stderr,
    )
    raise SystemExit(1)
reject_external_data("overlay", info)
PY
	then
		fail "base and persistent overlay validation failed"
	fi
}

validate_immutable_stage()
{
	local path
	local relative
	local boot_dir=$guest_dir/boot
	local manifest=$guest_dir/SHA256SUMS
	local -a immutable_paths=(
		base.img
		base-format.txt
		seed.img
		user-data
		meta-data
		boot/vmlinuz
		boot/initramfs.img
		boot/cmdline.txt
		source.txt
	)

	assert_trusted_directory "$boot_dir" "boot directory"
	for relative in "${immutable_paths[@]}"; do
		path=$guest_dir/$relative
		if [[ -L $path || ! -f $path || ! -s $path || ! -r $path ]]; then
			fail "missing, empty, unreadable, or symlinked immutable stage file: $path"
		fi
		assert_not_group_or_other_writable "$path" "immutable stage file"
	done
	if [[ -L $manifest || ! -f $manifest || ! -s $manifest ||
	      ! -r $manifest ]]; then
		fail "missing, empty, unreadable, or symlinked manifest: $manifest"
	fi
	assert_not_group_or_other_writable "$manifest" "immutable manifest"

	validate_manifest
}

read_guest_user()
{
	local value

	if ! value=$(
		"$python_bin" - "$guest_dir/source.txt" <<'PY'
import re
import sys

path = sys.argv[1]
try:
    data = open(path, "rb").read(65537)
except OSError as exc:
    print(f"cannot read guest source metadata {path}: {exc}", file=sys.stderr)
    raise SystemExit(1)
if len(data) > 65536:
    print(f"guest source metadata is too large: {path}", file=sys.stderr)
    raise SystemExit(1)
if b"\r" in data or b"\0" in data:
    print(f"guest source metadata contains a forbidden CR or NUL: {path}",
          file=sys.stderr)
    raise SystemExit(1)
prefix = b"Guest user: "
matches = [line[len(prefix):] for line in data.split(b"\n")
           if line.startswith(prefix)]
if len(matches) != 1:
    print(f"{path} must contain exactly one 'Guest user: ...' line",
          file=sys.stderr)
    raise SystemExit(1)
user = matches[0]
if not re.fullmatch(rb"[a-z_][a-z0-9_-]{0,31}", user):
    print(f"{path} contains an unsafe guest account name", file=sys.stderr)
    raise SystemExit(1)
if user == b"root":
    print(f"{path} must not name root as the guest account", file=sys.stderr)
    raise SystemExit(1)
sys.stdout.buffer.write(user)
PY
	); then
		fail "cannot derive a safe non-root guest user from manifested source.txt"
	fi
	guest_user=$value
}

load_manifested_guest_user()
{
	validate_immutable_stage
	read_guest_user
}

validate_stage()
{
	validate_immutable_stage
	if [[ -L $overlay || ! -f $overlay || ! -s $overlay ||
	      ! -r $overlay || ! -w $overlay ]]; then
		fail "overlay must be a non-empty, readable, writable regular file: $overlay"
	fi
	assert_owned_path "$overlay" "persistent overlay"
	assert_not_group_or_other_writable "$overlay" "persistent overlay"

	validate_storage
	read_ascii_single_line \
		"$guest_dir/boot/cmdline.txt" "staged kernel command line" staged_cmdline
	if [[ $staged_cmdline == ' '* || $staged_cmdline == *' ' ]]; then
		fail "staged kernel command line must not start or end with whitespace."
	fi
	read_guest_user
}

resolve_executable()
{
	local requested=$1
	local label=$2
	local output_variable=$3
	local candidate
	local resolved

	reject_line_breaks "$label" "$requested"
	if [[ -z $requested || $requested == -* ]]; then
		fail "$label must name an executable: $requested"
	fi
	if [[ $requested == */* ]]; then
		candidate=$requested
	else
		candidate=$(command -v "$requested") ||
			fail "$label not found: $requested"
	fi
	if [[ ! -f $candidate || ! -x $candidate ]]; then
		fail "$label is not an executable file: $candidate"
	fi
	resolved=$(realpath -e -- "$candidate") ||
		fail "cannot resolve $label: $candidate"
	if [[ ! -f $resolved || ! -x $resolved ]]; then
		fail "$label target is not executable: $resolved"
	fi
	printf -v "$output_variable" '%s' "$resolved"
}

validate_launch_environment()
{
	fedora_cpu=${K3_FEDORA_CPU-host}
	fedora_vcpus=${K3_FEDORA_VCPUS-4}
	fedora_memory=${K3_FEDORA_MEMORY-4G}
	fedora_ssh_port=${K3_FEDORA_SSH_PORT-2222}
	fedora_aia=${K3_FEDORA_AIA-plic}
	fedora_extra_append=${K3_FEDORA_EXTRA_APPEND-}

	if [[ ! $fedora_cpu =~ ^[A-Za-z0-9._+-]+(,[A-Za-z0-9._+-]+(=[A-Za-z0-9._+-]+)?)*$ ]]; then
		fail "K3_FEDORA_CPU is not a safe QEMU CPU token: $fedora_cpu"
	fi
	if [[ ! $fedora_vcpus =~ ^[1-8]$ ]]; then
		fail "K3_FEDORA_VCPUS must be an integer from 1 through 8."
	fi
	if [[ ! $fedora_memory =~ ^[1-9][0-9]*[kKmMgGtTpPeE]?$ ]]; then
		fail "K3_FEDORA_MEMORY must be a positive integral QEMU size token."
	fi
	validate_ssh_port
	case "$fedora_aia" in
	plic|aplic-imsic)
		;;
	*)
		fail "K3_FEDORA_AIA must be plic or aplic-imsic."
		;;
	esac
	reject_line_breaks K3_FEDORA_EXTRA_APPEND "$fedora_extra_append"
}

validate_ssh_port()
{
	fedora_ssh_port=${K3_FEDORA_SSH_PORT-2222}
	if [[ ! $fedora_ssh_port =~ ^[1-9][0-9]*$ ]] ||
	   ((fedora_ssh_port < 1024 || fedora_ssh_port > 65535)); then
		fail "K3_FEDORA_SSH_PORT must be an integer from 1024 through 65535."
	fi
}

validate_stop_environment()
{
	fedora_stop_timeout=${K3_FEDORA_STOP_TIMEOUT-60}
	fedora_ssh_identity=${K3_FEDORA_SSH_IDENTITY-}
	validate_ssh_port
	if [[ ! $fedora_stop_timeout =~ ^[1-9][0-9]*$ ]] ||
	   ((fedora_stop_timeout < 1 || fedora_stop_timeout > 3600)); then
		fail "K3_FEDORA_STOP_TIMEOUT must be an integer from 1 through 3600."
	fi
	reject_line_breaks K3_FEDORA_SSH_IDENTITY "$fedora_ssh_identity"
	if [[ -n $fedora_ssh_identity ]] &&
	   { [[ -L $fedora_ssh_identity ]] ||
	     [[ ! -f $fedora_ssh_identity ]] ||
	     [[ ! -r $fedora_ssh_identity ]]; }; then
		fail "K3_FEDORA_SSH_IDENTITY must name a readable regular non-symlink file."
	fi
}

validate_terminate_environment()
{
	fedora_terminate_timeout=${K3_FEDORA_TERMINATE_TIMEOUT-30}
	if [[ ! $fedora_terminate_timeout =~ ^[1-9][0-9]*$ ]] ||
	   ((fedora_terminate_timeout < 1 ||
	     fedora_terminate_timeout > 3600)); then
		fail "K3_FEDORA_TERMINATE_TIMEOUT must be an integer from 1 through 3600."
	fi
	if [[ ${K3_FEDORA_ACK_UNCLEAN_TERMINATION-} != YES ]]; then
		fail "terminate requires K3_FEDORA_ACK_UNCLEAN_TERMINATION=YES for this invocation."
	fi
}

validate_kvm_host()
{
	local host_system
	local host_arch
	local kvm_fd

	host_system=$(uname -s)
	host_arch=$(uname -m)
	if [[ $host_system != Linux || $host_arch != riscv64 ]]; then
		fail "KVM launch requires a riscv64 Linux host, not $host_system/$host_arch."
	fi
	if [[ ! -c /dev/kvm ]]; then
		fail "missing KVM character device: /dev/kvm"
	fi
	if [[ ! -r /dev/kvm || ! -w /dev/kvm ]]; then
		fail "the current user lacks read-write access to /dev/kvm."
	fi
	if ! exec {kvm_fd}<>/dev/kvm; then
		fail "the current user cannot open /dev/kvm read-write."
	fi
	exec {kvm_fd}>&-
}

validate_ssh_port_available()
{
	if ! "$python_bin" - "$fedora_ssh_port" <<'PY'
import socket
import sys

port = int(sys.argv[1])
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", port))
except OSError as exc:
    print(f"localhost TCP port {port} is unavailable: {exc}", file=sys.stderr)
    raise SystemExit(1)
finally:
    sock.close()
PY
	then
		fail "SSH forwarding port is already occupied or unavailable: $fedora_ssh_port"
	fi
}

acquire_launch_lock()
{
	exec {launch_lock_fd}>>"$lock_file"
	if ! flock -n "$launch_lock_fd"; then
		fail "another run or resume operation holds the guest launch lock: $lock_file"
	fi
	launch_lock_held=1
}

print_login_guidance()
{
	printf 'Normal login: ssh -p %s %s@127.0.0.1\n' \
		"$fedora_ssh_port" "$guest_user" >&2
	printf 'Clean shutdown command: ssh -p %s %s@127.0.0.1 sudo -n systemctl poweroff\n' \
		"$fedora_ssh_port" "$guest_user" >&2
	printf '%s\n' \
		'Use this script'\''s stop action for managed clean shutdown.' \
		'Use terminate only for a guest that never reaches SSH.' >&2
}

refuse_unsafe_runtime()
{
	case "$runtime_state" in
	active)
		fail "guest is already running as identity-matched PID $runtime_pid."
		;;
	orphan-active)
		fail "$runtime_detail Refusing launch until runtime identity is repaired."
		;;
	identity-mismatch)
		fail "$runtime_detail Refusing to treat PID $runtime_pid as this guest."
		;;
	unverifiable)
		fail "$runtime_detail Refusing unsafe runtime cleanup or launch."
		;;
	stale)
		cleanup_stale_runtime ||
			fail "cannot safely clean stale runtime state: $runtime_detail"
		;;
	inactive)
		;;
	*)
		fail "internal error: unknown runtime state: $runtime_state"
		;;
	esac
}

run_guest()
{
	local action=$1
	local qemu_request=$2
	local qemu_bin
	local qemu_img_bin
	local qemu_rc
	local machine
	local kernel_append
	local staged_cmdline
	local -a qemu_args

	validate_launch_environment
	resolve_executable "$qemu_request" QEMU_BIN qemu_bin
	resolve_executable qemu-img qemu-img qemu_img_bin
	ensure_runtime_dir
	acquire_launch_lock
	classify_runtime
	refuse_unsafe_runtime
	validate_stage
	validate_ssh_port_available
	validate_kvm_host

	case "$fedora_aia" in
	plic)
		machine=virt
		;;
	aplic-imsic)
		machine=virt,aia=aplic-imsic
		;;
	esac
	kernel_append="$staged_cmdline console=ttyS0,115200n8"
	if [[ -n $fedora_extra_append ]]; then
		kernel_append+=" $fedora_extra_append"
	fi

	qemu_args=(
		-machine "$machine"
		-accel kvm
		-cpu "$fedora_cpu"
		-smp "$fedora_vcpus"
		-m "$fedora_memory"
		-nographic
		-chardev "stdio,id=serial0,signal=off"
		-serial chardev:serial0
		-monitor none
		-no-reboot
		-qmp "unix:$qmp_socket,server=on,wait=off"
		-pidfile "$pid_file"
		-kernel "$guest_dir/boot/vmlinuz"
		-initrd "$guest_dir/boot/initramfs.img"
		-append "$kernel_append"
		-drive "file=$overlay,format=qcow2,if=none,id=root"
		-device "virtio-blk-device,drive=root"
		-drive "file=$seed_image,format=raw,if=none,id=seed,readonly=on"
		-device "virtio-blk-device,drive=seed"
		-netdev \
		"user,id=net0,hostfwd=tcp:127.0.0.1:${fedora_ssh_port}-:22"
		-device "virtio-net-device,netdev=net0"
	)

	if [[ $action == resume ]]; then
		printf '%s\n' \
			"resume means booting the same persistent overlay again: $overlay" \
			'No QEMU snapshot-resume operation will be used.' >&2
	else
		printf 'Booting persistent overlay in the foreground: %s\n' \
			"$overlay" >&2
	fi
	print_login_guidance

	if (
		exec {launch_lock_fd}>&-
		exec "$qemu_bin" "${qemu_args[@]}"
	); then
		qemu_rc=0
	else
		qemu_rc=$?
	fi

	classify_runtime
	case "$runtime_state" in
	stale)
		cleanup_stale_runtime ||
			fail "cannot safely clean stale runtime state: $runtime_detail"
		;;
	inactive)
		;;
	active|orphan-active|identity-mismatch|unverifiable)
		fail "QEMU returned, but runtime state is unsafe: $runtime_detail"
		;;
	*)
		fail "internal error after QEMU exit: $runtime_state"
		;;
	esac
	return "$qemu_rc"
}

status_guest()
{
	validate_ssh_port
	classify_runtime
	case "$runtime_state" in
	active)
		load_manifested_guest_user
		printf 'active: PID %s is identity-matched to %s\n' \
			"$runtime_pid" "$overlay"
		if [[ ! -S $qmp_socket ]]; then
			printf 'warning: QMP socket is not ready: %s\n' "$qmp_socket" >&2
		fi
		print_login_guidance
		return 0
		;;
	stale)
		printf 'inactive/stale: %s\n' "$runtime_detail"
		printf '%s\n' \
			'status is read-only; stale PID/QMP paths were left untouched.'
		return 1
		;;
	inactive)
		printf 'inactive: %s\n' "$runtime_detail"
		return 1
		;;
	orphan-active|identity-mismatch|unverifiable)
		printf 'unsafe: %s\n' "$runtime_detail" >&2
		return 2
		;;
	*)
		fail "internal error: unknown runtime state: $runtime_state"
		;;
	esac
}

matching_guest_has_exited()
{
	local pid=$1
	local identity_status
	local scan_status

	if pid_identity_matches "$pid"; then
		return 1
	else
		identity_status=$?
	fi
	case "$identity_status" in
	1|2)
		if scan_for_matching_process; then
			wait_detail="PID $scanned_pid still matches the guest."
			return 2
		else
			scan_status=$?
			if [[ $scan_status -eq 1 ]]; then
				wait_detail="no identity-matched guest process remains."
				return 0
			fi
			wait_detail=$runtime_detail
			return 2
		fi
		;;
	3)
		wait_detail=$pid_identity_detail
		return 3
		;;
	*)
		fail "internal error: unexpected wait identity status: $identity_status"
		;;
	esac
}

wait_for_guest_exit()
{
	local pid=$1
	local timeout=$2
	local deadline=$((SECONDS + timeout))
	local exit_status

	while :; do
		if matching_guest_has_exited "$pid"; then
			return 0
		else
			exit_status=$?
		fi
		if ((exit_status > 1)); then
			return 2
		fi
		if ((SECONDS >= deadline)); then
			return 1
		fi
		sleep 1
	done
}

ssh_guest_poweroff()
{
	local -a ssh_args=(
		-T
		-o BatchMode=yes
		-o ConnectionAttempts=1
		-o ConnectTimeout=10
		-o StrictHostKeyChecking=accept-new
		-o "UserKnownHostsFile=$known_hosts_file"
		-o GlobalKnownHostsFile=/dev/null
		-p "$fedora_ssh_port"
	)

	if [[ -n $fedora_ssh_identity ]]; then
		ssh_args+=(
			-o IdentitiesOnly=yes
			-i "$fedora_ssh_identity"
		)
	fi
	ssh_args+=(
		"$guest_user@127.0.0.1"
		sudo -n systemctl poweroff
	)
	ssh "${ssh_args[@]}"
}

print_stop_failure_guidance()
{
	printf 'Manual clean shutdown: ssh -p %s %s@127.0.0.1 sudo -n systemctl poweroff\n' \
		"$fedora_ssh_port" "$guest_user" >&2
	printf '%s\n' \
		'If the guest never reaches SSH, use terminate only with the required acknowledgment.' \
		'terminate is not an in-guest filesystem shutdown and may require guest filesystem recovery.' >&2
}

stop_guest()
{
	local identity_status
	local ssh_status
	local wait_status

	validate_stop_environment
	classify_runtime
	case "$runtime_state" in
	active)
		;;
	stale)
		if cleanup_stale_runtime; then
			printf 'inactive: removed proven-stale PID/QMP paths for %s\n' \
				"$guest_dir" >&2
			return 1
		fi
		printf 'unsafe: %s\n' "$runtime_detail" >&2
		return 2
		;;
	inactive)
		printf 'inactive: no recorded guest is available to stop.\n' >&2
		return 1
		;;
	orphan-active|identity-mismatch|unverifiable)
		printf 'unsafe: %s\n' "$runtime_detail" >&2
		printf '%s\n' \
			'No shutdown request was sent to an unverified process.' >&2
		return 2
		;;
	*)
		fail "internal error: unknown runtime state: $runtime_state"
		;;
	esac

	load_manifested_guest_user
	ensure_known_hosts_file
	if pid_identity_matches "$runtime_pid"; then
		:
	else
		identity_status=$?
		printf 'unsafe: PID %s failed the final identity check before SSH: %s\n' \
			"$runtime_pid" "$pid_identity_detail" >&2
		printf 'No SSH shutdown request was sent (identity status %s).\n' \
			"$identity_status" >&2
		return 2
	fi
	if ssh_guest_poweroff; then
		ssh_status=0
	else
		ssh_status=$?
	fi
	if [[ $ssh_status -ne 0 && $ssh_status -ne 255 ]]; then
		printf 'error: in-guest poweroff command failed with SSH status %s.\n' \
			"$ssh_status" >&2
		print_stop_failure_guidance
		return 1
	fi
	if [[ $ssh_status -eq 0 ]]; then
		printf 'In-guest poweroff command completed for identity-matched PID %s; waiting for QEMU exit.\n' \
			"$runtime_pid" >&2
	else
		printf 'SSH disconnected with status 255 during shutdown of identity-matched PID %s; verifying QEMU exit.\n' \
			"$runtime_pid" >&2
	fi
	if wait_for_guest_exit "$runtime_pid" "$fedora_stop_timeout"; then
		if cleanup_stale_runtime; then
			printf 'stopped: guest exited after the in-guest poweroff request and stale runtime paths were removed.\n'
		else
			printf 'stopped: guest exited after the in-guest poweroff request; runtime cleanup was deferred: %s\n' \
				"$runtime_detail"
		fi
		return 0
	else
		wait_status=$?
	fi
	if [[ $wait_status -eq 2 ]]; then
		printf 'error: guest process identity became unsafe while waiting: %s\n' \
			"$wait_detail" >&2
	else
		printf 'error: guest did not shut down within %s seconds.\n' \
			"$fedora_stop_timeout" >&2
		if [[ $ssh_status -eq 255 ]]; then
			printf '%s\n' \
				'The SSH disconnect was not accepted as success because the identity-matched QEMU process did not exit.' >&2
		fi
	fi
	print_stop_failure_guidance
	return 1
}

terminate_guest()
{
	local identity_status
	local signal_status
	local wait_status

	validate_terminate_environment
	classify_runtime
	case "$runtime_state" in
	active)
		;;
	stale|orphan-active|identity-mismatch|unverifiable)
		printf 'unsafe: %s\n' "$runtime_detail" >&2
		printf '%s\n' \
			'No signal was sent because the exact recorded process identity is not safely active.' >&2
		return 2
		;;
	inactive)
		printf 'inactive: no recorded guest is available to terminate.\n' >&2
		return 1
		;;
	*)
		fail "internal error: unknown runtime state: $runtime_state"
		;;
	esac

	if pid_identity_matches "$runtime_pid"; then
		:
	else
		identity_status=$?
		printf 'unsafe: PID %s failed the final identity check: %s\n' \
			"$runtime_pid" "$pid_identity_detail" >&2
		printf 'No signal was sent (identity status %s).\n' \
			"$identity_status" >&2
		return 2
	fi
	if [[ ! $runtime_pid =~ ^[1-9][0-9]*$ ]]; then
		fail "internal error: validated runtime PID is not a positive integer"
	fi

	printf '%s\n' \
		"warning: sending one SIGTERM to identity-matched QEMU PID $runtime_pid." \
		'This closes QEMU and its block backends but is not an in-guest filesystem shutdown.' \
		'Guest filesystem recovery may be required; no signal escalation will be attempted.' >&2
	if kill -TERM "$runtime_pid"; then
		signal_status=0
	else
		signal_status=$?
	fi
	if [[ $signal_status -ne 0 ]]; then
		printf 'error: SIGTERM could not be sent to identity-matched PID %s (status %s).\n' \
			"$runtime_pid" "$signal_status" >&2
		printf '%s\n' \
			'No further signal or process-control action was attempted.' >&2
		return 1
	fi

	if wait_for_guest_exit "$runtime_pid" "$fedora_terminate_timeout"; then
		if cleanup_stale_runtime; then
			printf 'terminated: QEMU exited after SIGTERM and stale runtime paths were removed.\n'
		else
			printf 'terminated: QEMU exited after SIGTERM; runtime cleanup was deferred: %s\n' \
				"$runtime_detail"
		fi
		return 0
	else
		wait_status=$?
	fi
	if [[ $wait_status -eq 2 ]]; then
		printf 'error: guest process identity became unsafe while waiting: %s\n' \
			"$wait_detail" >&2
	else
		printf 'error: identity-matched PID %s did not exit within %s seconds after SIGTERM.\n' \
			"$runtime_pid" "$fedora_terminate_timeout" >&2
	fi
	printf '%s\n' \
		'No escalation beyond the one numeric-PID SIGTERM was attempted.' >&2
	return 1
}

if [[ ${1:-} == -h || ${1:-} == --help ]]; then
	if [[ $# -ne 1 ]]; then
		usage_error "--help does not accept additional arguments."
	fi
	usage
	exit 0
fi

if [[ $# -lt 2 || $# -gt 3 ]]; then
	usage_error "expected ACTION GUEST_DIR [QEMU_BIN]."
fi

action=$1
guest_dir_arg=$2
case "$action" in
run|resume)
	if [[ $# -eq 3 ]]; then
		qemu_request=$3
		if [[ -z $qemu_request ]]; then
			usage_error "QEMU_BIN must not be empty."
		fi
	else
		qemu_request=qemu-system-riscv64
	fi
	;;
status|stop|terminate)
	if [[ $# -ne 2 ]]; then
		usage_error "QEMU_BIN is accepted only by run and resume."
	fi
	;;
*)
	usage_error "unknown action: $action"
	;;
esac

if [[ $EUID -eq 0 ]]; then
	fail "refusing to run as root; use an ordinary user."
fi

for tool in flock python3 realpath rm stat; do
	require_command "$tool"
done
python_bin=$(command -v python3)
launch_lock_held=0

case "$action" in
run|resume)
	for tool in mkdir qemu-img sha256sum uname; do
		require_command "$tool"
	done
	;;
status)
	require_command sha256sum
	;;
stop)
	for tool in sha256sum sleep ssh; do
		require_command "$tool"
	done
	;;
terminate)
	require_command sleep
	;;
esac

resolve_guest_dir "$guest_dir_arg"

case "$action" in
run|resume)
	if run_guest "$action" "$qemu_request"; then
		exit 0
	else
		exit $?
	fi
	;;
status)
	if status_guest; then
		exit 0
	else
		exit $?
	fi
	;;
stop)
	if stop_guest; then
		exit 0
	else
		exit $?
	fi
	;;
terminate)
	if terminate_guest; then
		exit 0
	else
		exit $?
	fi
	;;
esac
