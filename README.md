<!-- SPDX-License-Identifier: GPL-2.0-only -->

# K3-CoM260 notes and tools

A collection of what I learn and do with the **SpacemiT K3-CoM260**:
board notes, hardware findings, firmware and OS bring-up, recovery procedures,
and assorted tools, scripts, and patches.

This is an evolving resource for sharing practical work with the board,
rather than a single software project.

## Documentation and tools

**Start with the [Fedora developer wiki](https://github.com/xjamesmorris/k3-com260-info/wiki).**
Its new-reader route is **Fedora 45-first**: a fresh installation of the
pinned image into **two existing NVMe partitions** from a Linux maintenance
host, using the public helpers. That route was **performed end to end on
October 20, 2026**, and its pinned 7.3.0 fan-control upgrade was booted on
October 21; creating the partitions, other kinds of maintenance host
and whole-disk imaging remain unverified. Read the
[installation orientation](https://github.com/xjamesmorris/k3-com260-info/wiki/Install-Fedora)
and [F45 recipe's recorded scope](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#readiness-and-recorded-scope)
before any installation work. No Fedora 44 installation or shrink step is
required for new F45 starters.

The wiki also covers hardware setup, maintenance, diagnostics, development,
and optional virtualization. “Default” means these documentation entry points
only: it does not change saved U-Boot defaults or remove F44. The canonical
source lives in
[`wiki/`](wiki/Home.md); its [maintenance tools](tools/wiki/README.md) validate
the separate GitHub Wiki projection. Editing or pushing this repository does
not itself publish the wiki. This is an unofficial, user-developed resource,
not an official Fedora Project guide.

The focused standalone documents and tools remain available:

- [Fedora 45 support bundle](fedora-45/README.md): public helpers and
  [exact image/package pins](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/files/sources.lock.json),
  with a [bounded host result record](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/RESULTS.md).
  The maintained command source is the
  [Fedora 45 recipe](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe),
  not this inventory.
- [Fedora 44 archive](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-44-Archive):
  the retained September 25 bring-up, source-built KVM host, and persistent
  Fedora guest. Its [standalone how-to](k3-com260-fedora-howto/README.md)
  remains preserved with helper scripts and the
  [kernel configuration and 14-patch bundle](k3-com260-fedora-howto/files/kernel/README.md).
  These are optional historical development references, not F45 requirements.
- [Tools](tools/README.md): Bianbu factory flashing using stock `fastboot`
  and USB header-button control, with usage, safety limits, and recorded results.
- [k3ctl](tools/k3ctl/README.md): ESP32-C3 firmware, a Python client, udev
  rules, and hardware-free tests for USB button control on the Firefly carrier.
  **Only `reset` has been tested on hardware so far**; recovery, power control,
  and the other functions remain unverified. It is not integrated into the
  flashing script.
- [Flashing development context](tools/k3-flash-bianbu-HANDOFF.md): protocol
  findings, design decisions, and ideas for further work.

The archived F44 command authority retains the
[`Fedora-Recipe` wiki slug](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe)
and public baseline `57400da095e944c75e63154b1c187e18a3ac3359`.
Its unchanged directory is `k3-com260-fedora-howto/`; after setting
`WORK` in its workstation setup, use this path instead of the guide's
`docs/k3-fedora-howto` path:

```sh
export HOWTO="$WORK/k3-com260-info/k3-com260-fedora-howto"
```

More board notes, scripts, and patches will be added as the work develops.

## External Resources

- [Bo Gan's collection of docs](https://github.com/ganboing/K3-Docs) and & great info on firmware hacking, JTAG, etc. Look there if you are unable to find or reach a vendor document due to CN server / network overload, which seems to happen at times.

- [Fedora RISC-V SIG](https://fedoraproject.org/wiki/Architectures/RISC-V),  home & starting point for RISC-V on Fedora specifically.

- [SpaceMit K3 Forums](https://forum.spacemit.com/c/25-category/25), lots of good info in a mixture of languages, with English well-supported. Protip: use an agent to summarize & translate activity there.

  
## Hardware and results

The flashing and Fedora bring-up work was done with a
**K3-CoM260 on a Firefly carrier**.
Carrier-specific wiring and procedures may not apply to other setups.
The tool documentation distinguishes image checksums pinned in the manifest
from actual flash and boot results.

The **October 20, 2026 F45 record** is a fresh installation of the
non-official community Beta image
`Fedora-Server-Host-Omni-45-20260923.2.riscv64.raw.xz` into two existing
NVMe partitions, p4 (`/boot`) and p5 (Btrfs root), made with the public
helpers from a Fedora 44 maintenance host on p1–p3 of the same disk, with
Bianbu Minimal K3 v4.0.1 non-UEFI firmware. One bootstrap boot of
`7.2.7-300.0.riscv64.omni.fc45.riscv64`, the exact COPR build `11035571`
update to `7.2.8-300.0.riscv64.omni.fc45.riscv64` and three attended 7.2.8
boots recorded NVMe, network/SSH, and **host KVM initialization only**.
Afterwards the partition table, all 116 F44 `/boot` and `/boot/efi` files
and the raw Bianbu UFS ESP were byte-identical to the before-state. The
earlier **October 19** side-by-side bring-up on the same partitions, made
before the public helpers existed, remains recorded. There is no F45 QEMU,
guest, or persistence result. On **October 21** the pinned 7.3.0 upgrade
(COPR build `11177969`, `7.3.0-65.1.riscv64.omni.fc45.riscv64`) was
installed from 7.2.8 and booted once, with the kernel controlling the fan.

Creating the partitions, other maintenance hosts and whole-disk imaging
(the image's own p2/p3 layout) have **not** been performed. The fan runs at
full speed under 7.2.7 and 7.2.8; the 7.3.0 upgrade adds kernel fan
control. Thermal limits remain, and no unattended-operation assurance is
made.

The archived F44 how-to records a **September 25, 2026 snapshot**. Its
historical stages ran on hardware, but the portable bundle was not rerun
end to end. Neither release record validates arbitrary newer inputs,
other carriers, production use, or hostile-guest isolation.

**Factory flashing erases NOR firmware and all UFS contents.** Read the
[tool documentation](tools/README.md) before using the script.

## Contributing

Corrections, patches, and additional hardware results are welcome. Include
the module, carrier, relevant firmware or OS versions, and what you tried.
For patches, identify the target project and revision.

Agent-assisted contributions must follow the [agent guidance](AGENTS.md) and
[LLM policy](LLM-POLICY.md), which adopts the Linux kernel's requirements.
An LLM is a tool: the human contributor remains the author responsible for
reviewing, understanding, and publishing the assisted material.

## License

GPL-2.0-only. See [LICENSE](LICENSE).
