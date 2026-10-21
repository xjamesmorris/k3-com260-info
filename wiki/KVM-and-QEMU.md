<!-- SPDX-License-Identifier: GPL-2.0-only -->

# KVM and QEMU

This page is for virtualization developers and security researchers comparing
**F45 host initialization only** with the **archived F44 full persistent
guest result**. KVM is optional for an F45 developer-host installation.
Neither result is a general claim that any K3 kernel can run any RISC-V
guest, and a host banner is not a guest-workload test.

F45 installation/update commands belong to the
[Fedora 45 recipe](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe).
The generated [Fedora-Recipe](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe)
remains the sole command authority for the historical F44 installation,
source-built host transition and guest workflow, accessible through the
[F44 archive](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-44-Archive).

## F45 host initialization, not a guest result

The [public F45 records](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/RESULTS.md)
of October 19 and 20 use Beta image
`Fedora-Server-Host-Omni-45-20260923.2.riscv64.raw.xz`, bootstrap
`7.2.7-300.0.riscv64.omni.fc45.riscv64`, then COPR build
`11035571`, `7.2.8-300.0.riscv64.omni.fc45.riscv64`.
Each record has one bootstrap boot and three attended updated-host boots;
`/dev/kvm` and host KVM initialization were observed. The October 19
updated-host banner reported RVH, Sv39x4 G-stage, 14-bit VMIDs and AIA with
seven guest external interrupts; the October 20 record notes the hypervisor
extension, Sv39x4 G-stage paging and 14-bit VMIDs. On October 21 the
pinned 7.3.0 upgrade (COPR build `11177969`) booted once with the same KVM
banner.

**Not recorded on F45:** QEMU version, guest launch, CPU filter, guest
interrupt mode, vCPUs/RAM, workload, guest network, or persistent
shutdown/resume. Do not apply the archived CPU workaround or copy its checks
into the F45 row. The October 20 fresh installation into existing p4/p5
partitions validates the host installation route, not a guest workload.
Under 7.2.x the fan runs at full speed; 7.3.0 adds kernel fan control, but
there is no sustained-load thermal qualification, which matters for long
guest workloads.

## Keep the three stages separate

These are the **archived F44 stages**, not F45 installation requirements.

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

The first row is explicitly **host-only F45**, not a published guest result.
The two archived F44 rows retain their public result statements and check
coverage, not an unpublished test log. Both F44 rows use the same
Firefly/NVMe host and Fedora 44 Cloud June 4 image. The guest kernel's `fc43`
suffix is intentional: it is the value in that public image record.

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
| F45 host initialization only | `7.2.8-300.0.riscv64.omni.fc45.riscv64`, COPR build `11035571`, and `7.3.0-65.1.riscv64.omni.fc45.riscv64`, COPR build `11177969`; 7.2.7 bootstrap recorded separately | Not recorded | Not tested / not recorded | Not recorded | Host AIA initialization observed; guest PLIC/AIA setting not recorded | Not recorded | No guest storage or persistence tests recorded. | No guest network tests recorded. | [F45 host results](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/RESULTS.md) and [exact pins](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/files/sources.lock.json) | `/dev/kvm` and host initialization only; no QEMU launch, guest workload, CPU-filter validation, guest isolation or persistence claim. |
| Full Fedora, recorded PLIC path | `7.3.0-rc4-k3-kvm-host-a1`, pinned source plus 14 patches | Fedora `10.2.2-1.fc44` | Fedora 44 Cloud; `6.19.8-200.0.riscv64.fc43.riscv64` | `host,svpbmt=false,zicbom=false,zicbop=false,zicboz=false` | `plic`; QEMU `virt` | 4 / 4 GiB | The captures show virtio disks and the Btrfs root mounted from the 20 GiB guest disk. The recipe records persistent `overlay.qcow2` backed by `base.img` and clean shutdown/resume. | The captures show `eth0` up with a guest address and an SSH terminal. The recipe records QEMU user networking, guest SSH through K3 loopback port 2222, the workstation tunnel, and guest package installation. | [Guest captures](https://github.com/xjamesmorris/k3-com260-info/tree/57400da095e944c75e63154b1c187e18a3ac3359/files/f44-kvm-guest-01) and [recorded procedure/result scope](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/README.md#prepare-and-run-the-persistent-guest) | The captures do not show the host launch command/package, overlay backing check, forwarding/tunnel path, package-install transcript, clean shutdown/resume, disk-integrity or throughput tests, restart count, or stress duration. |
| Full Fedora, tested AIA alternative | `7.3.0-rc4-k3-kvm-host-a1`, pinned source plus 14 patches | Fedora `10.2.2-1.fc44` | Fedora 44 Cloud; `6.19.8-200.0.riscv64.fc43.riscv64` | `host,svpbmt=false,zicbom=false,zicbop=false,zicboz=false` | `aplic-imsic`; QEMU `virt,aia=aplic-imsic` | 4 / 4 GiB | Same persistent disk, resumed after PLIC shutdown. Separate AIA-mode storage and persistence check outputs are not recorded. | Same networking configuration; separate AIA-mode network check outputs are not recorded. | [Public statement that AIA is the tested alternative](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/README.md#prepare-and-run-the-persistent-guest) | The public statement does not supply an independent per-mode validation matrix. Do not transfer every PLIC check into this row as a measured AIA result. |

**Additional settings belong only to both archived F44 guest rows, not the
F45 host-only row:** Sstc stays enabled;
`K3_FEDORA_EXTRA_APPEND` is
`earlycon=sbi unaligned_scalar_speed=slow unaligned_vector_speed=unsupported`.
These are additions to the staged guest command line and the runner's serial
console argument. They and the CPU filter are **compatibility workarounds,
not tuning suggestions**. Keep the full recipe environment for every launch,
including `resume`; this page intentionally does not duplicate its commands.

No selftest counts, other guest images, unfiltered full-Fedora results, or
larger vCPU configurations are established by this matrix. The historical
F44 stages ran on hardware, but the portable bundle was not rerun end to end.
The separate F45 row establishes none of those guest checks.

## What is virtualized

QEMU's [RISC-V `virt` documentation](https://www.qemu.org/docs/master/system/riscv/virt.html)
describes a synthetic machine, not a K3 carrier model. PLIC and APLIC/IMSIC
are guest-visible interrupt-controller choices; a successful AIA guest is
not proof of device assignment or complete physical-board emulation.

The historical F44 [public runner](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/scripts/k3-run-fedora-guest.sh)
requires KVM and uses `-accel kvm`; it does not fall back to TCG software
emulation. Conversely, a generic QEMU/TCG boot on a workstation would not
prove K3 KVM functionality. A summary from `fastfetch`, supported ISA bits,
or the existence of `/dev/kvm` is not a substitute for the guest result.

## Persistent disk and SSH identity

This section explains the **archived F44 guest workflow**, not a tested F45
guest procedure.

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

Start with the [historical F44 report preparation example](https://github.com/xjamesmorris/k3-com260-info/wiki/Contributing-Upstream#worked-preparation-fedora-guest-report).
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

**Applies to:** 8 GiB K3-CoM260 on the recorded Firefly carrier, PCB revision unknown, Bianbu Minimal K3 v4.0.1 non-UEFI firmware and NVMe; F45 host-only initialization and the separately pinned historical F44 guest stack.

**Evidence:** Public October 21, 20 and 19 F45 host results/pins and preserved September 25 F44 PLIC/AIA result coverage and captures. QEMU/KVM references retain their September 27 source review and explain concepts, not new tests.

**Source review:** 2026-10-21.

**Hardware observation:** 2026-10-21 one attended 7.3.0 fan-control boot with KVM host initialization only; 2026-10-20 fresh F45 installation into existing p4/p5 partitions: 7.2.7 bootstrap, exact 7.2.8 update and three attended 7.2.8 boots, with KVM host initialization only; 2026-10-19 F45 bootstrap/three pre-fan updated-host boots without guest testing; 2026-09-25 archived F44 guest snapshot. No F45 guest workload was tested.

**Destructive operations:** None on this page. The linked installation recipe reformats two selected NVMe partitions; guest operation writes a persistent guest disk. Forced termination can lose guest writes.

**Previous:** [Kernel and device-tree development](https://github.com/xjamesmorris/k3-com260-info/wiki/Kernel-and-Device-Tree-Development).
**Next:** [AI and toolchains](https://github.com/xjamesmorris/k3-com260-info/wiki/AI-and-Toolchains).
