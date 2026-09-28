<!-- SPDX-License-Identifier: GPL-2.0-only -->

# KVM and QEMU

This page is for virtualization developers and security researchers evaluating
the recorded KVM result. That result is a **full, persistent Fedora guest on
an exact patched host**, not a general claim that any K3 kernel can run any
RISC-V guest.
The [public snapshot](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/README.md#recorded-snapshot)
is the evidence. The generated
[Fedora recipe](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe)
is the sole installation, host-transition, and guest-command authority.

## Keep the three stages separate

1. **Bootstrap Fedora:** the July 31 Fedora 44 Omni image uses
   `7.1.5-201.0.riscv64.omni.fc44.riscv64`. Its separately prepared DTB keeps
   **both `dldo4` and `hub-reset`** enabled. This is not an untouched-image boot
   or proof that either property alone suffices. Follow
   [image preparation](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#image-and-prepare-the-nvme)
   and [bootstrap boot](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#boot-the-bootstrap-fedora-host).
   The recipe explicitly says not to launch guests on this kernel.
2. **Transition to the KVM host:** install and temporarily boot
   `7.3.0-rc4-k3-kvm-host-a1` beside the bootstrap kernel. Its
   [public source and configuration record](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/files/kernel/README.md)
   pins `kvm-riscv/linux` commit
   `a5f72fd298f6bd02e6d30599dafb43cfa16576b6` plus 14 patches: PHY helpers,
   PCIe enablement, CoM260 PCIe DT changes, and the isolated `dldo4` change.
   It does not include the unrelated USB/hub series. Follow
   [build, installation, temporary selection, and host checks](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#build-and-install-the-kvm-host).
   A working host, an AIA banner, and access to `/dev/kvm` are prerequisites,
   **not guest-workload proof**.
3. **Run the full Fedora guest:** use the complete recorded environment in
   [guest preparation and operation](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#prepare-and-run-the-persistent-guest).
   The helper's generic bare-`host` default is not this tested recipe.
   Neither a host-only check nor a minimal guest result establishes the full
   Fedora result.

The host boot selection is temporary on every reset. Do not save the U-Boot
environment; the existing saved path may return to Bianbu. See
[maintenance boundaries](https://github.com/xjamesmorris/k3-com260-info/wiki/Maintain-and-Update).

## Published guest results

These rows describe the public result statements and their check coverage,
not an unpublished test log. Both use the same Firefly/NVMe host and the
Fedora 44 Cloud June 4 image. The guest kernel's `fc43` suffix below is
intentional: it is the value in the public Fedora 44 image record.

The existing
[public guest capture set](https://github.com/xjamesmorris/k3-com260-info/tree/57400da095e944c75e63154b1c187e18a3ac3359/files/f44-kvm-guest-01)
is evidence consistent with the recorded **PLIC** boot, not a new run. Its
[guest dmesg](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/files/f44-kvm-guest-01/k3-dmesg.txt)
shows the Fedora guest kernel on QEMU `virt`, four CPUs, Sstc, the recorded
extra kernel arguments, a guest PLIC, virtio block devices, and the Btrfs root
mount. The
[fastfetch](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/files/f44-kvm-guest-01/k3-fastfetch.txt)
and
[inxi](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/files/f44-kvm-guest-01/k3-inxi.txt)
captures show Fedora 44 Cloud, four guest CPUs, about 4 GiB RAM, the guest
disk/root layout, `eth0` up, and an SSH terminal. They do not independently
establish the host-side launch, overlay backing relationship, forwarding
path, clean shutdown/resume, or the AIA alternative.

| Result | Host kernel | QEMU package | Guest type and kernel | CPU model/filter | PLIC/AIA setting | vCPUs / RAM | Storage and persistence checks | Network checks | Public source | Nonclaims and unknowns |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Full Fedora, recorded PLIC path | `7.3.0-rc4-k3-kvm-host-a1`, pinned source plus 14 patches | Fedora `10.2.2-1.fc44` | Fedora 44 Cloud; `6.19.8-200.0.riscv64.fc43.riscv64` | `host,svpbmt=false,zicbom=false,zicbop=false,zicboz=false` | `plic`; QEMU `virt` | 4 / 4 GiB | The captures show virtio disks and the Btrfs root mounted from the 20 GiB guest disk. The recipe records persistent `overlay.qcow2` backed by `base.img` and clean shutdown/resume. | The captures show `eth0` up with a guest address and an SSH terminal. The recipe records QEMU user networking, guest SSH through K3 loopback port 2222, the workstation tunnel, and guest package installation. | [Guest captures](https://github.com/xjamesmorris/k3-com260-info/tree/57400da095e944c75e63154b1c187e18a3ac3359/files/f44-kvm-guest-01) and [recorded procedure/result scope](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/README.md#prepare-and-run-the-persistent-guest) | The captures do not show the host launch command/package, overlay backing check, forwarding/tunnel path, package-install transcript, clean shutdown/resume, disk-integrity or throughput tests, restart count, or stress duration. |
| Full Fedora, tested AIA alternative | `7.3.0-rc4-k3-kvm-host-a1`, pinned source plus 14 patches | Fedora `10.2.2-1.fc44` | Fedora 44 Cloud; `6.19.8-200.0.riscv64.fc43.riscv64` | `host,svpbmt=false,zicbom=false,zicbop=false,zicboz=false` | `aplic-imsic`; QEMU `virt,aia=aplic-imsic` | 4 / 4 GiB | Same persistent disk, resumed after PLIC shutdown. Separate AIA-mode storage and persistence check outputs are not recorded. | Same networking configuration; separate AIA-mode network check outputs are not recorded. | [Public statement that AIA is the tested alternative](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/README.md#prepare-and-run-the-persistent-guest) | The public statement does not supply an independent per-mode validation matrix. Do not transfer every PLIC check into this row as a measured AIA result. |

**Additional settings belong to both rows:** Sstc stays enabled;
`K3_FEDORA_EXTRA_APPEND` is
`earlycon=sbi unaligned_scalar_speed=slow unaligned_vector_speed=unsupported`.
These are additions to the staged guest command line and the runner's serial
console argument. They and the CPU filter are **compatibility workarounds,
not tuning suggestions**. Keep the full recipe environment for every launch,
including `resume`; this page intentionally does not duplicate its commands.

No selftest counts, other guest images, unfiltered full-Fedora results, or
larger vCPU configurations are established by this matrix. The historical
stages ran on hardware, but the portable bundle was not rerun end to end.

## What is virtualized

QEMU's [RISC-V `virt` documentation](https://www.qemu.org/docs/master/system/riscv/virt.html)
describes a synthetic machine, not a K3 carrier model. PLIC and APLIC/IMSIC
are guest-visible interrupt-controller choices; a successful AIA guest is
not proof of device assignment or complete physical-board emulation.

The [public runner](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/scripts/k3-run-fedora-guest.sh)
requires KVM and uses `-accel kvm`; it does not fall back to TCG software
emulation. Conversely, a generic QEMU/TCG boot on a workstation would not
prove K3 KVM functionality. A summary from `fastfetch`, supported ISA bits,
or the existence of `/dev/kvm` is not a substitute for the guest result.

## Persistent disk and SSH identity

Keep `base.img` and `overlay.qcow2` together in the complete prepared guest
tree. **`resume` boots the same persistent disk again; it does not restore
guest RAM or a VM snapshot.** Guest writes remain in the overlay.

Use the recipe's authenticated guest SSH session for a clean guest shutdown,
wait for foreground QEMU to exit, then resume. Console escape, QMP quit, and
force-kill are not normal shutdown methods for this persistent disk.

The guest private key stays on the Linux workstation. Verify the K3 host key
through serial; for the guest, use a trusted fingerprint inspection path or
make an explicit trust-on-first-use decision over the verified tunnel.
Retain the guest-specific SSH identity and host-key alias. Never disable
host-key checking to suppress a changed-key warning.

The runner's optional `stop` operation needs a usable guest SSH identity or
agent **on the K3**; it cannot acquire the workstation's private key. Do not
assume that operation works merely because workstation-to-guest SSH works.
The [canonical guest section](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#prepare-and-run-the-persistent-guest)
explains the password-locked seeded account, tunnel, and manual identity
handling.

## Turn a result into useful development evidence

Start with the [worked Fedora report preparation](https://github.com/xjamesmorris/k3-com260-info/wiki/Contributing-Upstream#worked-preparation-fedora-guest-report).
Keep the host source/configuration, QEMU build, guest image/kernel, CPU
filter, interrupt mode, and actual checks together. Identify missing results
rather than filling them with another workload's success.
The upstream [KVM review checklist](https://docs.kernel.org/virt/kvm/review-checklist.html)
explains when selftests, kvm-unit-tests, userspace support, and regression
tests are expected; it is not a claim that those tests were run here.

This is trusted-guest bring-up material. It makes **no production,
hostile-guest isolation, VFIO, migration, or long-duration stability claim**.
Stop on a failed prerequisite or a different stack and use
[diagnostics](https://github.com/xjamesmorris/k3-com260-info/wiki/Diagnostics-and-Known-Limits),
not an improvised launch recipe.

## Technical notes

**Applies to:** 8 GiB K3-CoM260 on the recorded Firefly carrier, Bianbu Minimal K3 v4.0.1 non-UEFI firmware, Fedora on NVMe, and the pinned Fedora guest stack on this page.

**Evidence:** Recorded public Fedora result; upstream references explain concepts and contribution expectations, not additional board tests.

**Source review:** 2026-09-27.

**Hardware observation:** 2026-09-25 public bring-up snapshot; no new hardware testing for this page.

**Destructive operations:** None on this page. The linked installation recipe overwrites the selected NVMe disk; guest operation writes a persistent guest disk. Forced termination can lose guest writes.

**Previous:** [Kernel and device-tree development](https://github.com/xjamesmorris/k3-com260-info/wiki/Kernel-and-Device-Tree-Development).
**Next:** [AI and toolchains](https://github.com/xjamesmorris/k3-com260-info/wiki/AI-and-Toolchains).
