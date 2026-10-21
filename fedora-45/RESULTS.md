<!-- SPDX-License-Identifier: GPL-2.0-only -->

# Fedora 45 Beta: recorded host results

This is an original summary, for human review, of three attended Fedora 45
records on the K3-CoM260:

- **October 21, 2026 (UTC): the 7.3.0 fan-control upgrade**, installed from
  7.2.8 with the public helpers and booted once.
- **October 20, 2026 (UTC): fresh installation with the public helpers**
  into two existing NVMe partitions, then the bootstrap boot, first login,
  the exact kernel update and three 7.2.8 boots. This is the route the
  [Fedora 45 recipe](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe)
  documents.
- **October 19, 2026 (UTC): the earlier side-by-side bring-up**, made before
  the public helpers existed.

Fan control arrived with the October 21 upgrade; the October 19 and 20
boots ran 7.2.x kernels, with the fan at full speed. F45 guest workloads
were not tested.

## Recorded stack and input pins

| Component | Recorded input |
| --- | --- |
| Hardware | SpacemiT K3-CoM260, **8 GiB RAM**, **Firefly carrier**; physical PCB revision **unknown/not recorded**. |
| Firmware | **Bianbu Minimal K3 v4.0.1**, non-UEFI U-Boot route. |
| Image | Community-contributed, non-official Fedora RISC-V Beta image: **`Fedora-Server-Host-Omni-45-20260923.2.riscv64.raw.xz`**. |
| Compressed image size | **1,216,442,944 bytes**. |
| Image SHA-256 | `6f0ebebc251149ba814fcb0e73c2535bc0a65437eff4827bdc4496916a8eebca` |
| Bootstrap kernel | **`7.2.7-300.0.riscv64.omni.fc45.riscv64`**, supplied by that image. |
| Updated kernel | **`7.2.8-300.0.riscv64.omni.fc45.riscv64`**, COPR **build `11035571`**, project **`@forge-riscv-members/riscv64_omni_kernel`**, chroot **`fedora-45-riscv64`**. |
| Fan-control kernel | **`7.3.0-65.1.riscv64.omni.fc45.riscv64`**, COPR **build `11177969`**, project **`@forge-riscv-members/riscv64_omni_mainline_kernel`**, chroot **`fedora-45-riscv64`**. |

Public provenance references:

- [Pinned Fedora 45 Beta image](https://dl.fedoraproject.org/pub/alt/risc-v/releases/test/45_Beta/Server/riscv64/images/Fedora-Server-Host-Omni-45-20260923.2.riscv64.raw.xz).
- [COPR build 11035571](https://copr.fedorainfracloud.org/coprs/g/forge-riscv-members/riscv64_omni_kernel/build/11035571/).
- [COPR build 11177969](https://copr.fedorainfracloud.org/coprs/g/forge-riscv-members/riscv64_omni_mainline_kernel/build/11177969/).
- [Merge request `jmontleon/kernel-ark!1`](https://gitlab.com/jmontleon/kernel-ark/-/merge_requests/1),
  the CoM260 thermal-zone and fan-cooling change, merged into
  `fedora-7.3.y-riscv-omni.0` on October 20, 2026 at 03:50 UTC as
  `325489705745991fe8bfa862f6533e5a01eef00d`.

These are fixed test inputs, not instructions to substitute a newer compose
or kernel. Package identity is bound to the build, NEVRAs and recorded
artifact hashes; it does **not** establish an exact source Git head.

## October 21: 7.3.0 fan-control upgrade

| Item | Recorded |
| --- | --- |
| Starting point | The October 20 installation on p4/p5, with F44 on p1–p3 running at the start. Since October 20 only the 7.2.8 transfer bundle and install log had been removed from the F45 home directory. |
| Packages | The five binary RPMs of COPR build `11177969` named in the lock. Their hashes came from repository primary metadata with SHA-256 `44e0935a6d86f3d20904cf16aa0e03faa5b1f9b785d52b264140ddf2b3a15604`. Inspection reported `NOKEY` (key ID `787d2d64bbba6beb`). The RPM changelog lists `FEDORA: riscv: dts: spacemit: k3-com260: Add thermal zones and fan cooling`. |
| Boot DTB | The packaged `spacemit/k3-com260-ifx.dtb`: 47,633 bytes, SHA-256 `a096de8c2a6478c9a7f29e01a97f029449e114feba5faae6de8ab0ef726856ef`. It contains the thermal zones, the fan cooling map, `regulator-always-on` on `dldo4` and an always-on USB hub supply, and no `/hub-reset` node; no bootstrap DTB was made. The 7.2.8 packaged and bootstrap DTBs contain no thermal-zone, cooling-map or CTF2301 node. |
| Operation | The operator stopped autoboot for the 7.2.8 boot, ran the installer and the 7.2.8 reboot with sudo, pressed reset and judged the fan noise. An LLM coding assistant, with the operator's approval, rebooted F44 over SSH, ran the fetch, transfer, SSH checks and load test, stopped autoboot for the 7.3.0 boot and entered the U-Boot lines one at a time through the operator's serial session, checking each echo and output. |

The helper bytes used, as SHA-256 (the populate and bootstrap-DTB helpers
were not used):

| File | SHA-256 |
| --- | --- |
| `scripts/extract-riscv-zboot.sh` | `d2d50ba1d6827431eeee4752150a56d18944ad92cc55b7c8aaed4cb2e2f6e313` |
| `scripts/fetch-f45-copr-kernel.sh` | `657ecf22f14abcd861a89f61ecaf1b13063013729974676609fde8d157775bcc` |
| `scripts/transfer-f45-copr-kernel-to-k3.sh` | `f171cbc52ed933e6a0054dd535ebe27dbb698af18013f0178cddbf06f176bb8d` |
| `scripts/k3-install-rpm-kernel.sh` | `293151f0ca2970f4eb53476cf0dce709332a90390fde407d441109ba3013ead7` |
| `scripts/verify-f45-bundle.py` | `a1eaabafa2918d1da3ffa7170bf9eb326fadf70a67774ceb18dcb09df882e038` |
| `files/sources.lock.json` | `9ee86130da66f211e3d258e982d68c205e4afcdef661065f83cb9128983142c1` |

| Time (UTC) | Step | Recorded result |
| --- | --- | --- |
| 06:27 | Fetch, on the workstation | `fetch-f45-copr-kernel.sh --build 11177969` downloaded the five RPMs; bytes and RPM metadata matched the lock. |
| 06:49:41 | 7.2.8 boot | The documented 7.2.8 sequence, with the October 20 load sizes and `initrd_size=2ec9220`; SSH at 06:50:06. |
| about 06:50 | Transfer | `transfer-f45-copr-kernel-to-k3.sh --build 11177969`; the remote RPMs re-verified against the transferred lock. |
| 07:02–07:05 | Install | The operator ran `k3-install-rpm-kernel.sh --build 11177969` with sudo. DNF completed, skipping OpenPGP checks for the five locally verified packages. The packaged DTB matched the lock and no bootstrap DTB was created. Raw Image 63,361,024 bytes, host-only initramfs 53,388,814 bytes; `/boot/dtb` still pointed at 7.2.7; 7.2.7 and 7.2.8 stayed installed. |
| about 07:27–07:30 | Reboot | After `sudo systemctl reboot` the console stopped at `reboot: Restarting system` until the operator pressed reset. Autoboot was stopped with `s`. |
| 07:31:36 | 7.3.0 `booti` | Addresses unchanged; PCIe-0 Gen3 x4 link up; `fsuuid nvme 0:4` printed the `/boot` UUID; loads of exactly 47,633, 63,361,024 and 53,388,814 bytes; `initrd_size=32ea60e`; the documented `bootargs`. Login prompt at 07:32:05, 28 seconds later. |
| 07:32:51 | SSH checks | Exact release, root p5 `[/root]` and `/boot` p4 with the expected UUIDs; `/boot/dtb` still 7.2.7; `running`, no failed units, no FAT mounts, fwupd masked. Startup 24.96 seconds (kernel 1.48, initrd 6.52, userspace 16.95); DHCPv4 lease at 24.3 seconds. |
| 07:34:27–07:40:35 | Fan test | 15 seconds idle, 120 seconds of eight `yes` processes, then 4 minutes of cooldown, sampled every 5–10 seconds. |

### October 21 observations

- **Thermal zones and fan:** seven thermal zones (`top`, `vpu`, `gpu`,
  `cluster0`–`cluster3`), all `step_wise`; `lm63` and `k3_tsensor` loaded
  automatically. The `ctf2301` cooling device (states 0–255) is bound only to
  `cluster0`: an active trip at 35 °C and passive trips at 40, 50, 60 and
  70 °C, each with 5 °C hysteresis, select fan-state ranges 0–50, 64–75,
  102–128, 179–204 and 255. The other zones have one 40 °C passive trip and
  no cooling device. The CTF2301 hwmon device (`lm63` driver) reported
  `pwm1` equal to the cooling state, `pwm1_enable` 1 and the fan speed.
- **Idle and load:** at a 47–48 °C `cluster0` idle (other zones 44–47 °C)
  the state was 78 and the fan turned at 3,824–3,846 rpm. Within 5 seconds of
  starting eight `yes` processes the state rose to 105 (4,873–4,909 rpm);
  `cluster0` peaked at 58 °C and the other zones at 51–55 °C, so the 60 °C
  trip was not reached. About 2 minutes after the load ended the zones were
  back at 44–48 °C, but the state stayed at 105, consistent with the 50 °C
  trip's hysteresis: `cluster0` did not fall below 45 °C.
- **Noise:** the operator found the fan much quieter than under 7.2.x at
  idle, and audibly faster under load.
- **USB:** the DWC3 controller at `0x81400000` probed, with no deferred-probe
  warning: a 5 Gb/s root hub and a USB 3.0 hub (`2109:0817`) enumerated. No
  USB transfer was tested.
- **Kernel messages:** 33 kernel lines at warning priority or higher (24 in
  the first 7.2.8 boot). New compared with 7.2.8:
  `cma: Failed to reserve 64 MiB`,
  `irq_aclint_sswi: unable to create muxed IPIs`,
  `OF: of_irq_init: Failed to init /soc/interrupt-controller@f181c000`, a
  second `at24` `supply vcc not found` and two ACPI `_DSM` evaluation
  failures. The reserved-memory overlap, PCIe `of_irq_parse_pci`, fusb301,
  ONIE EEPROM and UFS RPMB messages remained. There was no thermal, `lm63`
  or `k3_tsensor` warning; in user space, irqbalance logged
  `thermal: failed to receive messages`. The effects of the new warnings
  were not investigated; none of the checks made failed.
- **KVM host initialization only:** `/dev/kvm` was present, with the same
  banner as 7.2.8. No guest was launched.
- **Reboot:** the 7.2.8 software reboot stopped at
  `reboot: Restarting system` until the operator pressed reset.

Not established by this run: more than one 7.3.0 boot, sustained or
long-duration load, the 60 and 70 °C trips, fan-failure or fail-safe
behavior, unattended operation, USB data transfer, any F45 guest workload,
and a post-run comparison of the partition table and protected files (the
board was left running 7.3.0).

## October 20: fresh installation with the public helpers

| Item | Recorded |
| --- | --- |
| Board and firmware | The stack above; U-Boot banner 2022.10, built May 21, 2026. |
| Targets | Existing NVMe **p4** (3 GiB, previously the October 19 F45 `/boot`) and **p5** (64 GiB, previously its Btrfs root), both reformatted. F44 occupied p1–p3 of the same disk. |
| Maintenance host | Fedora 44, kernel `7.1.5-201.0.riscv64.omni.fc44.riscv64`, running on the same board from p1–p3. |
| fwupd choice | `K3_F45_FWUPD=mask`, written into the new root before its first boot. |
| Operation | The operator was present for every boot and handled power, autoboot interruption, passwords and sudo. An LLM coding assistant, with the operator's approval, ran the populate helper, the SSH checks and the transfer, and entered the U-Boot lines one at a time through the operator's serial session, checking each echo and output. Every value below was read from command output or the console log, except the fan, which the operator observed. |

The helper bytes used, as SHA-256:

| File | SHA-256 |
| --- | --- |
| `scripts/populate-f45-volumes.sh` | `af8a7709387277996ad78282e7e7b45c8ca625eb1c658d18608145007bd02d5f` |
| `scripts/make-bootstrap-dtb.sh` | `7edabf4bf57be1e4f9d7a57539b5f1c5be06e976ece0975198ecf2318f95a2b8` |
| `scripts/extract-riscv-zboot.sh` | `d2d50ba1d6827431eeee4752150a56d18944ad92cc55b7c8aaed4cb2e2f6e313` |
| `scripts/fetch-f45-copr-kernel.sh` | `b73196336a8f7001524c081c04eb16be6bef03e67e039c3da95cbffd7ec5ddf7` |
| `scripts/transfer-f45-copr-kernel-to-k3.sh` | `a6fa5ab3dd3446581b068b49e585dacd38a25a5b7639f6ddb017d165ee9f10c7` |
| `scripts/k3-install-rpm-kernel.sh` | `e73cb1aff124426c520d7655e9eb8d18320baf2b6f4b772924f01bfd3b409438` |
| `scripts/verify-f45-bundle.py` | `e649eec59a754c19bcfaf71a05af7d808844a5f21cfaf354b1417d0430fc6142` |
| `files/sources.lock.json` | `76e91b5d7ab32286761b65dd83ccd48efa42b1d4d3043e1b4ff489a44b0f25b4` |

| Time (UTC) | Step | Recorded result |
| --- | --- | --- |
| 07:35 | Before-state from F44, then `populate-f45-volumes.sh --check` | Partition-table dump, hashes of all 116 F44 `/boot` and `/boot/efi` files and a raw hash of the Bianbu UFS ESP saved. The check passed and wrote nothing. |
| 19:49:27–19:50:53 | `populate-f45-volumes.sh` | Exit 0 after 86 seconds. Both filesystems were recreated; four root references were rewritten (fstab, both BLS entries, `/etc/kernel/cmdline`); the fwupd masks were written. Raw Image 63,283,200 bytes, bootstrap DTB 40,109 bytes (exactly two added lines), the image's initramfs 78,670,210 bytes. A read-only re-inspection found SELinux labels preserved, `/boot/dtb` pointing at 7.2.7, no leftover mounts or loop devices, and the partition table and protected files unchanged. |
| 20:45:49 | 7.2.7 `booti` | Addresses `0x138000000` (DTB), `0x140000000` (Image), `0x130000000` (ramdisk); `fsuuid nvme 0:4` printed the new `/boot` UUID; all three loads matched the expected byte counts. Login prompt at 20:46:13, 24 seconds later. |
| about 20:48–21:05 | First login and SSH | `fedora` with the default password `linux` logged in; `sudo -v` worked. The ED25519 host-key fingerprint printed on serial matched the network key. Key login worked after the second `ssh-copy-id`. The system was `running` with no failed units, startup 26.6 seconds, DHCPv4 lease at 26.4 seconds. |
| about 21:05–21:20 | Fetch, transfer, install | The workstation fetched and lock-verified the five RPMs (`NOKEY`); the remote copies matched. Btrfs error counters were zero. DNF completed; the installer copied the bootstrap DTB because the packaged 7.2.7 and 7.2.8 DTBs were byte-identical. 7.2.8 raw Image 63,287,296 bytes, host-only initramfs 49,058,336 bytes; `/boot/dtb` still pointed at 7.2.7. |
| 21:58:44, 22:55:37, 23:12:03 | Three 7.2.8 boots | Each after `systemctl reboot`, autoboot interruption and the full checked sequence. Login prompt about 22 seconds after `booti` each time; startup 23.1, 23.5 and 22.9 seconds; DHCPv4 at about 22.8, 23.2 and 22.7 seconds; `running`, no failed units, no FAT mounts, fwupd masked. |
| 23:13–23:21 | Return to F44 | A reboot without interrupting autoboot started F44 from the unchanged saved environment. The partition table, all 116 F44 boot files and the raw UFS ESP were byte-identical to the 07:35 record. |

### October 20 observations

- **First login:** `root` is locked; `fedora` is in `wheel`, with
  `%wheel ALL=(ALL) ALL`; there is no initial-setup or cloud-init step; the
  machine ID and SSH host keys are created at first boot; SSH password
  authentication is enabled. The password-change step was not exercised in
  this run.
- **First-boot presets:** systemd's first-boot preset ran while the root was
  still read-only and logged `Read-only file system` for several units.
  Afterwards `lvm-devices-import.path` and `.service`,
  `remote-integritysetup.target` and `systemd-tpm2-clear.service` were
  disabled although their presets enable them. None is used by this route.
- **Other storage:** with the offline fwupd masks, no boot mounted a FAT
  filesystem, and the protected partitions were unchanged afterwards. This is
  not a general isolation guarantee.
- **Network:** all four F45 boots had DHCPv4 within about 23–26 seconds.
  Back on F44, which uses the same interface and address, the lease came
  only after about 145 seconds. The cause was not determined.
- **Fan and thermal:** the fan ran at full speed, loudly, in every F45 boot,
  and F44's own fan service slowed it again. Neither kernel exposed SoC
  thermal zones (only `cooling_device0`).
- **USB:** DWC3 `81400000.usb3` stayed in deferred probe; only USB2
  enumerated.
- **Kernel warnings:** the same set in every boot: reserved-memory overlap
  reports from the firmware DT, PCIe `of_irq_parse_pci` errors, fusb301 Type-C
  probe messages (absent in one boot), UFS RPMB/BOOT WLUN messages, an ONIE
  EEPROM header warning and the deferred USB3 probe.
- **KVM host initialization only:** `/dev/kvm` was present, with the banner
  reporting the hypervisor extension, Sv39x4 G-stage paging and 14-bit
  VMIDs. No guest was launched.
- **Console:** vendor U-Boot prefixes output with `[ seconds ]` timestamps,
  sometimes between `=> ` and the echoed command.
- **SSH key installation:** the first `ssh-copy-id` attempt left no
  `~/.ssh` on the K3; the cause was not determined. The second worked.

Not established by this run: creating partitions on a blank disk, any other
maintenance host, whole-disk imaging, unattended or loaded operation, thermal
protection, power-loss behavior, USB3, any F45 guest workload, and any other
carrier, module variant, firmware or image.

## October 19: side-by-side bring-up

### What was actually installed and booted

The Linux-workstation-assisted installation retained F44 on NVMe partitions
**p1–p3**, adding an ext4 F45 `/boot` on **p4** and Btrfs F45 root on **p5**.
Image contents were populated into those new filesystems. F45 omitted
`/boot/efi` on this direct non-UEFI route. Temporary U-Boot selections loaded
F45 from `nvme 0:4`; the saved F44 boot default was retained.

| Stage | Recorded observation on October 19, UTC |
| --- | --- |
| 7.2.7 bootstrap | One boot at approximately **07:00** reached the expected p5 root and p4 `/boot`. Network and SSH worked; the five-minute check reported a running system, no failed units or kernel warnings, and `/dev/kvm`. |
| 7.2.8 installation | Five hash-verified binary RPMs (`kernel`, `kernel-core`, `kernel-modules`, `kernel-modules-core`, `kernel-modules-extra`) were installed at **07:34**, retaining 7.2.7 alongside them. |
| 7.2.8 smoke boots | **Three attended, pre-fan boots**, at **07:38, 07:51 and 08:03**; each was recorded as exceeding ten minutes. Expected F45 mounts and zero Btrfs device errors were recorded across the three boots. No lockup, RCU stall or oops was reported at the recorded checks. |

The bootstrap DTB added `regulator-always-on` to `dldo4` and a root-level
`/hub-reset`, preserving the packaged DTB separately. Packaged DTBs from
these exact 7.2.7 and 7.2.8 inputs compared byte-identical, justifying reuse
of that prepared bootstrap DTB for 7.2.8—not for arbitrary future kernels.
The RPM installation alone did not create that separately patched DTB.

| Locally prepared artifact | Recorded size |
| --- | ---: |
| 7.2.7 raw `Image` / initramfs | 63,283,200 / 78,670,210 bytes |
| 7.2.8 raw `Image` / host-only initramfs | 63,287,296 / 49,159,528 bytes |
| Pre-fan bootstrap DTB | **40,109 bytes** |

The 7.2.8 initramfs included Btrfs and NVMe support. These generated-file
sizes are observations, not universally expected output after regeneration.
The installer left `/boot/dtb` pointing at 7.2.7, so that symlink alone
cannot identify the DTB used for a temporary boot.

### Observations and important exceptions

- **Network:** Ethernet link worked. Boots 1–2 obtained DHCPv4 in roughly
  **4–9 seconds**; boot 3 took about **7.5 minutes**, without intervention.
  Link and IPv6 were already up at 18 seconds on that boot. Prompt IPv4/SSH
  availability is therefore not established for every boot.
- **Storage/PCIe:** NVMe p1–p5 and both PCIe root complexes enumerated.
  These short checks are not endurance, performance or power-loss tests.
- **Unexpected ESP access:** on the first 7.2.8 boot, an RTC correction
  triggered catch-up timers; fwupd/udisks2 briefly mounted both the F44 NVMe
  ESP and the Bianbu UFS ESP **read-write**. F45 subsequently had
  `fwupd.service` and `fwupd-refresh.timer` masked; boot 2 showed no FAT
  mounts or `/run/media` units. This release-scoped workaround is not an
  assurance that other disks are isolated or untouched.
- **USB:** only the xHCI USB2 root hub appeared. DWC3 `81400000.usb3`
  remained deferred, as in the earlier F44 observation. USB3 enablement is
  **not** a result of these boots.
- **Thermal:** neither kernel exposed SoC thermal zones. A recorded NVMe
  temperature of 43.9 °C is not a SoC measurement or thermal qualification.
  There is **no thermal-protection, fail-safe or unattended-operation
  assurance**. Cooling-fan work was deferred at that time; see the
  October 21 record above.
- **KVM host initialization only:** `/dev/kvm` and the initialization banner
  reported the hypervisor extension, Sv39x4 G-stage, 14-bit VMIDs and AIA
  with seven guest external interrupts. No QEMU/guest tuple, guest launch,
  workload, guest networking or persistent shutdown/resume was tested on
  this F45 host. Initialization is not a guest-isolation or security
  assurance.

The [historical F44 how-to](../k3-com260-fedora-howto/README.md) retains its
separate source-built host and persistent-guest workflow. Its guest results
must not be relabeled as F45 results or prerequisites.

## Fresh-install and provenance limits

The October 20 run validates the **volume route**: the public helpers
populating two existing partitions, booted with the documented U-Boot
sequence. Whole-disk imaging (`/boot` on p2, root on p3) and creating the
partitions were not performed and remain unverified.

Recorded binary-RPM hash matches are not independent package-signature
verification: inspection reported `NOKEY` for both kernel builds. The original recorded SRPM URL
was unavailable (HTTP 404) during the October 19 work; the five-binary-RPM
installation did not require it. A differently hashed replacement SRPM was
not accepted as the recorded source artifact. Source provenance therefore
remains limited; no source reconstruction or new artifact verification is
claimed here.

The SPDX declaration covers this newly written summary, not the Fedora
image or COPR packages. It does not assign licenses or authorship to those
artifacts. Accuracy, privacy and provenance still require human review;
this summary supplies no publication approval. Nothing here generalizes the
Firefly-carrier observations to other carriers, module variants, firmware or
images.
