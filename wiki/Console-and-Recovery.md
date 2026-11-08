<!-- SPDX-License-Identifier: GPL-2.0-only -->

# Console and recovery

This page is for operators establishing the recorded serial-console checkpoint
on the Firefly-carrier K3-CoM260 before Fedora bring-up. Start with the normal
path that keeps matching firmware. Treat recovery as a conditional path for
needed restoration or a deliberate human choice. The header mapping is
conditional and specific to the recorded carrier context rather than a
universal CoM260 pinout.

The [F45 host record](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/RESULTS.md)
uses the same non-UEFI firmware/serial boundary.
Its [tested installation into two existing NVMe partitions](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#readiness-and-recorded-scope)
keeps matching firmware and boots by temporary U-Boot commands; changing
the documentation default is not permission to reflash or change the saved
boot environment.

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
| 5, 6 | `BMCU_ACOK`, `AUTO_ON_DIS` | Power policy jumper; see the observed bridged/unbridged behavior below |
| 7, 9, 11 | GND | Adapter ground and the ground return for recovery/reset |
| 8 | Firefly `RST`; vendor `PMIC_RST_OUTn` | Momentary connection to confirmed GND for reset |
| 10 | Firefly `FC_REC`; vendor `FORCE_RECOVERY` | Hold to confirmed GND for recovery entry |
| 12 | `SLEEP/WAKE` | Power-button signal; see the bounded results below |

Use suitable jumper leads or normally-open momentary switches for the
control signals. The serial adapter connects only RX, TX and ground:
**leave its power/VCC lead disconnected**.

**Disconnect DC before changing the pins 5/6 jumper.** Its configuration is
not a universal power-on fix. With pins unbridged, DC reapplication
auto-booted in the October 31 test, but pin 12 pulses did not wake after
software shutdown. In the November 6-7 bridged test, DC insertion stayed
off and a 300 ms press powered on; however, the same press still failed
after software shutdown until DC was removed/reconnected.

The October 30 bridged power-on failure is retained; its pulse length and
software/build versions were not recorded. The V2.1 guide's button-power-on
bridge guidance works in some newly observed off states, not all. See the
[bounded hardware results](https://github.com/xjamesmorris/k3-com260-info/blob/main/tools/k3ctl/README.md#recorded-hardware-results)
and the attended sequence below before choosing the jumper behavior.

## Normal setup: keep working firmware

1. Match the conditional header reference above against the actual carrier. Use the [hardware scope](https://github.com/xjamesmorris/k3-com260-info/wiki/Hardware-and-Setup#identify-the-hardware-first), not the module name, to decide whether these notes apply. Stop if the wiring cannot be matched.
2. Connect a **3.3 V USB serial adapter to RX, TX, and ground only**: adapter TX to board RX, adapter RX to board TX. Do not connect the adapter's power/VCC lead. A different electrical interface is not a substitute.
3. Open the console at **115200 8N1, no flow control**, using the [F45 recipe's workstation and serial instructions](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#workstation-serial-and-notation). Record the firmware banner/version and confirm that autoboot can be interrupted. Keep physical reset or power-cycle access.

**Checkpoint:** readable, interruptible **Bianbu Minimal K3 v4.0.1 non-UEFI
U-Boot**, matching the recorded route. If it matches, do not factory-flash
simply to start the guide; continue to
[Install Fedora](https://github.com/xjamesmorris/k3-com260-info/wiki/Install-Fedora).
Working but different or unidentified firmware needs the decision below.
All Fedora boot choices in the recipes are temporary: never run `env save` or
`saveenv`. Reset follows the existing saved path, which may boot Bianbu or
the retained F44 installation, not the temporarily selected F45 kernel.

## Optional USB button controller

The standalone
[`k3ctl` bundle](https://github.com/xjamesmorris/k3-com260-info/blob/main/tools/k3ctl/README.md)
provides ESP32-C3 firmware, a Linux Python client, a udev rule and
hardware-free client tests for the matching Firefly-carrier header.
**Reset is maintainer-reported working; power-button behavior depends on
the off state.** Earlier October 30-31 failures are preserved in the
bundle's recorded results. The reset test date and software/build versions
remain unrecorded. Match the header and read the bundle's electrical and
device-selection cautions before connecting anything.

### Attended power and display results

On **November 6-7, 2026 (operator local time, UTC-08:00)**, the maintainer
observed the following sequence on the K3-CoM260/Firefly setup with
**pins 5/6 bridged**, using k3ctl firmware **1.1** and no power-sense wire:

| Test | Result |
| --- | --- |
| Reconnect DC | K3 stayed off |
| 300 ms power press after DC insertion | Powered on with console output |
| While running: 300 ms, 1 s, repeated 3 s, 6 s | K3 stayed on |
| While running: 12 s | Power disappeared abruptly |
| 300 ms after forced power-off | Powered on again |
| Software shutdown using `sudo poweroff` in the K3 console | Powered off |
| 300 ms after software shutdown with DC connected | Stayed off; no console output |
| Remove/reconnect DC, then 300 ms | Powered on with console output |

The 12-second hold is **forced power loss**, not clean shutdown. The exact
forced-off threshold and the reason software-shutdown wake differs remain
unresolved. All pulses received `OK` replies, which alone do not establish
the K3 outcome. These explicit-pulse tests do not validate the named
`power on|off|force-off` modes or their defaults.

The dongle build used Arduino CLI 1.5.1, ESP32 core 3.3.12 and U8g2 2.36.19,
with `esp32:esp32:esp32c3:CDCOnBoot=cdc,FlashSize=4M`. The current K3
firmware and OS/kernel revision were not freshly established; do not borrow
the October 31 kernel version for this November result. Carrier PCB
revision remains unknown.

The maintainer also confirmed the **1.1** startup logo and readable
three-second `ERR` event. After the **1.1.1** upload on November 7, the logo
started bright, dimmed after about 10 seconds and moved horizontally
without clipping. An `ERR` event restarted the bright centred idle period
before dimming/movement resumed. Both uploads were made with the header
wires disconnected. Power sensing and the sensed `ON` screensaver remain
untested on hardware; recovery, external LED/DC-switch operation and
broader fault behavior are also unverified.

Video: [Watch k3ctl v1.1.1 on YouTube](https://www.youtube.com/shorts/w1l2AyYvUZs).

Unplugging DC produced a `PWR` display event in the 1.1 test. With power
sensing disabled, that is consistent with the monitored line going low,
not proof of a physical button press or a measured K3 power state.

It is optional, not a Fedora prerequisite, and does not carry the K3 serial
console. Keep the separate serial adapter and physical reset/power access.
An abrupt reset can lose unsaved data and follows the existing saved boot
path, not the last temporary Fedora selection. The flashing script does not
invoke `k3ctl` and has no `-r` option; this does not replace the recorded
manual recovery sequence below or establish a new factory-flash result.

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

## Technical notes

**Applies to:** Recorded Firefly-carrier K3-CoM260 kit; carrier PCB revision unknown. The serial/boot route uses Bianbu Minimal K3 v4.0.1 non-UEFI U-Boot. The November k3ctl results use dongle firmware 1.1/1.1.1, ESP32 core 3.3.12 and U8g2 2.36.19; current K3 firmware and OS/kernel revision were not freshly established.

**Evidence:** Public October 20 and October 19 F45 host scope, preserved Fedora serial/Firefly recovery records, earlier maintainer-reported k3ctl results, and the November 6-7 attended power/display sequence documented here and in the public k3ctl guide. The conditional V2.1 UART/ground reference retains its September 27 review; pins 5, 6 and 12 were source-checked on 2026-10-30. November outcomes do not establish voltage or back-feed safety.

**Source review:** 2026-11-07.

**Hardware observation:** November 6-7, 2026, operator local time (UTC-08:00): the bounded bridged power sequence and dongle display results above. October 30-31 power-on failures remain recorded, with October 31 using k3ctl 1.0 and Fedora 45 kernel 7.3.0-65.1.riscv64.omni.fc45; the earlier reset test date and October 30 command/timing/build are unknown. Existing October 20/19 F45 temporary boots and the September 25 archived serial/boot snapshot are unchanged; the successful Minimal v4.0.1 factory flash still lacks a test date. No further hardware was operated during this documentation update, and no USB recovery result was added.

**Destructive operations:** Serial setup does not erase storage. USB reset, a long forced-off hold or cutting DC can lose unsaved data. Disconnect DC before changing the jumper, and disconnect K3 header wires before uploading/resetting the dongle. Factory flashing rewrites NOR and all UFS, including the saved environment, and attempts an EC firmware update; NVMe is not erased.

**Previous:** [Hardware and setup](https://github.com/xjamesmorris/k3-com260-info/wiki/Hardware-and-Setup).
**Next:** [Install Fedora](https://github.com/xjamesmorris/k3-com260-info/wiki/Install-Fedora).
