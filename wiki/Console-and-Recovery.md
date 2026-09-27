<!-- SPDX-License-Identifier: GPL-2.0-only -->

# Console and recovery

**Applies to:** Recorded Firefly-carrier K3-CoM260 kit and Bianbu Minimal K3 v4.0.1 non-UEFI U-Boot; carrier PCB revision unknown.

**Evidence:** Public Fedora serial/boot and Firefly recovery records; UART/ground pin numbers from the conditional V2.1 vendor reference below.

**Source review:** 2026-09-27.

**Hardware observation:** 2026-09-25 serial/boot snapshot; successful Minimal v4.0.1 factory flash is recorded separately without a test date.

**Destructive operations:** Serial setup does not erase storage. Factory flashing rewrites NOR and all UFS, including the saved environment, and attempts an EC firmware update; NVMe is not erased.

## Conditional 12-pin header reference

**Use this mapping only if the Firefly-sold kit's header matches the reference
numbering and signals.** Locate pin 1 and establish the viewing orientation
from the actual carrier markings and matching diagram, not a guessed
left/right arrangement. Verify signal labels, ground and **3.3 V TTL** serial
levels before connecting. Stop on any mismatch or if these cannot be confirmed.
The carrier PCB model/revision remains unknown; this is not a universal CoM260
pinout and must not be applied to CORE-K3JD4-based products or other carriers.

The [public Firefly recovery record](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/tools/README.md#putting-the-board-in-recovery)
uses the carrier labels **FC_REC** for pin 10 and **RST** for pin 8. The
vendor guide names the corresponding signals **FORCE_RECOVERY** and
**PMIC_RST_OUTn**. UART, ground, and vendor signal names below come from
section 5.3 of the
[SpacemiT reference-kit guide V2.1, July 16, 2026](https://cdn-resource.spacemit.com/file/product/K3/k3_com260_ug_en.pdf),
which names product version `K3-CoM260_P1_LP5315B_32X2_v03_20260312`, not this
carrier's PCB identity. Its V2.0 revision, March 19, 2026, corrected the UART
RX/TX positions; do not reuse an older diagram.

| Reference pin | Firefly record / vendor signal | Connection or use after matching the header |
| --- | --- | --- |
| 3 | `UART0_RXD` (board RX) | Adapter **TX** to board RX |
| 4 | `UART0_TXD` (board TX) | Adapter **RX** to board TX |
| 7, 9, 11 | GND | Adapter ground and the ground return for recovery/reset |
| 8 | Firefly `RST`; vendor `PMIC_RST_OUTn` | Momentary connection to confirmed GND for reset |
| 10 | Firefly `FC_REC`; vendor `FORCE_RECOVERY` | Hold to confirmed GND for recovery entry |

Use suitable jumper leads or normally-open momentary switches for the two
control signals. The serial adapter connects only RX, TX and ground:
**leave its power/VCC lead disconnected**.

## Normal setup: keep working firmware

1. Match the conditional header reference above against the actual carrier. Use the [hardware scope](https://github.com/xjamesmorris/k3-com260-info/wiki/Hardware-and-Setup#identify-the-hardware-first), not the module name, to decide whether these notes apply. Stop if the wiring cannot be matched.
2. Connect a **3.3 V USB serial adapter to RX, TX, and ground only**: adapter TX to board RX, adapter RX to board TX. Do not connect the adapter's power/VCC lead. A different electrical interface is not a substitute.
3. Open the console at **115200 8N1, no flow control**, using the [recipe's workstation and serial instructions](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#workstation-serial-and-notation). Record the firmware banner/version and confirm that autoboot can be interrupted. Keep physical reset or power-cycle access.

**Checkpoint:** readable, interruptible **Bianbu Minimal K3 v4.0.1 non-UEFI
U-Boot**, matching the recorded route. If it matches, do not factory-flash
simply to start the guide; continue to
[Install Fedora](https://github.com/xjamesmorris/k3-com260-info/wiki/Install-Fedora).
Working but different or unidentified firmware needs the decision below.
All Fedora boot choices in the recipe are temporary: never run `env save` or
`saveenv`. Reset follows the existing saved path, which may boot Bianbu,
not either Fedora kernel.

## Decide whether recovery is needed

| Observation | Next decision |
| --- | --- |
| Required v4.0.1 non-UEFI U-Boot works, but Fedora does not boot | Stop at the failed recipe checkpoint. Check the selected Image/DTB/initramfs, actual load sizes and root UUID through the recipe; do not erase matching, working firmware. |
| Firmware boots, but its version/boot family differs or is unidentified | Record its banner and image identity, and stop outside this recorded route. A human may deliberately choose the documented [factory restore](https://github.com/xjamesmorris/k3-com260-info/wiki/Console-and-Recovery#factory-recovery-only-when-needed) to the recorded baseline after backing up needed NOR/UFS contents. That destructive choice is not the default or an automatic setup step. |
| Serial is silent | Recheck the matching carrier wiring, power and console settings. The recorded route removes microSD cards because non-vendor layouts stopped BootROM before serial output. Silence alone is not a reason to flash. |
| Fedora host works, but a guest fails | Use [KVM and QEMU](https://github.com/xjamesmorris/k3-com260-info/wiki/KVM-and-QEMU) and [Diagnostics and known limits](https://github.com/xjamesmorris/k3-com260-info/wiki/Diagnostics-and-Known-Limits). Factory flashing is not a guest repair step. |
| Existing firmware no longer boots and factory restoration is needed | Read the destructive scope and maintained flashing instructions below before entering recovery. |

## Factory recovery, only when needed

**This is a factory restore, not an NVMe repair or a Fedora rollback.**
The maintained
[flashing tool documentation on public `main`](https://github.com/xjamesmorris/k3-com260-info/blob/main/tools/README.md)
is the current command and safety authority. Its normal invocation erases NOR
firmware and all UFS contents, including the saved environment, while leaving
NVMe alone. Use it only for needed recovery or a human's deliberate choice to
restore the recorded baseline. Back up any NOR/UFS contents you need before
that choice; a working firmware mismatch does not authorize an automatic
restore.

The following physical entry sequence is the
[recorded Firefly 12-pin-header procedure](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/tools/README.md#putting-the-board-in-recovery).
It is historical procedure provenance, not a pinout for CORE-K3JD4-based
products or other carriers:

1. Hold **FC_REC, pin 10**, shorted to the carrier's identified **GND**.
2. Power on; if already powered, pulse **RST, pin 8**, to GND.
3. Release FC_REC.
4. Connect the carrier's USB-C port to the Linux workstation with a data-capable cable.

The tool guide's USB check should show `???????????? DFU download`; the
blank serial is normal. If no device appears, recheck recovery entry and the
data cable. `no permissions` indicates host USB-access permissions, not a
reason to change the wiring or repeatedly reset the board.

Use the documented
[requirements](https://github.com/xjamesmorris/k3-com260-info/blob/main/tools/README.md#requirements),
[preflight checks](https://github.com/xjamesmorris/k3-com260-info/blob/main/tools/README.md#verifying-before-you-write)
and [usage](https://github.com/xjamesmorris/k3-com260-info/blob/main/tools/README.md#usage)
from the maintained public `main` documentation.
`--check` stops before device traffic but can download and extract multi-GB
images; it is not a side-effect-free command preview or a hardware test.

The [recorded successful factory result](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/tools/README.md#status)
is retained as historical result provenance:
`Bianbu-Minimal-K3-v4.0.1-20260521183730`, full flash and UFS boot. Other
manifest pins do not establish successful flashing or booting. Follow the
maintained tool guide's completion and retry instructions, then re-establish
the normal serial checkpoint before returning to the Fedora recipe.

**Previous:** [Hardware and setup](https://github.com/xjamesmorris/k3-com260-info/wiki/Hardware-and-Setup).
**Next:** [Install Fedora](https://github.com/xjamesmorris/k3-com260-info/wiki/Install-Fedora).
