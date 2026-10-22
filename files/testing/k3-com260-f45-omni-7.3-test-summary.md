# SpacemiT K3 CoM260: Fedora 45 Omni 7.3 Kernel Test

**Test date:** October 21, 2026 PDT / October 22, 2026 UTC\
**Board:** SpacemiT K3 CoM260 IFX\
**Kernel:** `7.3.0-65.1.riscv64.omni.fc45.riscv64`\
**Source:** COPR project `@forge-riscv-members/riscv64_omni_mainline_kernel`\
**Result:** Thermal/fan support passed; native KVM partially passed with
unresolved SSTC and QEMU shutdown issues.

## Boot and system status

The COPR kernel was installed alongside the existing Fedora 45 kernel and
booted manually through U-Boot. The existing Fedora 45 7.2.8 kernel remains
the saved default and fallback.

The 7.3 kernel booted successfully from NVMe and reached a normal multi-user
system:

- Root filesystem and `/boot` mounted correctly.
- systemd reported `running`.
- No systemd units failed.
- NVMe, Ethernet, Wi-Fi PCIe, and `/dev/kvm` were present.
- The system remained stable for more than 55 minutes.
- No lockup, RCU stall, panic, Oops, Btrfs error, or NVMe error was observed.

The software reboot path still occasionally hangs at
`reboot: Restarting system`; a physical reset was required during this test.

## Kernel fan and thermal control

The packaged CoM260 device tree includes:

- `dldo4` marked always-on;
- the K3 thermal sensor;
- seven SoC thermal zones;
- the Sensylink CTF2301 fan controller at I2C address `0x4c`; and
- cooling maps linking `cluster0-thermal` to the CTF2301 cooling device.

The kernel loaded:

```text
k3_tsensor
lm63
```

The fan was controlled entirely by the kernel. No userspace fan daemon was
installed or running.

Representative steady-state readings were:

```text
Fan speed:          approximately 4,900 RPM
PWM:                100-105 / 255, approximately 39-41%
Fan controller:     approximately 33 C local, 35 C remote
SoC thermal zones:  approximately 45-50 C
```

This is a substantial improvement over the uncontrolled full-speed fan
behavior seen with the older kernel.

## Native KVM check

QEMU `11.0.93`, packaged as the Fedora 45 QEMU 11.1 RC3 build, was tested
with the previously validated `final-a4` RISC-V smoke guest.

### Unmasked host CPU

The first test used:

```text
-cpu host
```

KVM launched the guest, but the guest immediately took an illegal instruction
in:

```text
riscv_timer_starting_cpu()
```

The failure occurred after the guest reported that S-mode timer interrupts
were available through the SSTC extension. The guest then panicked.

This resembles the SSTC compatibility problem previously observed on the
older Omni 7.1.5 host.

### Compatibility CPU mask

The second test used:

```text
-cpu host,sstc=false,svpbmt=false
```

QEMU warned:

```text
KVM cannot disable extension sstc
```

Despite that warning, the guest booted successfully, reached userspace,
detected PLIC interrupt delivery, and emitted:

```text
KVM_GUEST_INIT_CONTRACT=k3-kvm-smoke-v3
KVM_GUEST_PLIC_RESULT=detected
KVM_GUEST_RESULT=PASS
K3_KVM_SMOKE_PASS:virt-plic-1vcpu-r01
```

This establishes that native KVM guest execution and PLIC delivery work on
the tested host with the compatibility mask.

However, after the guest requested poweroff, QEMU did not exit. The outer
120-second timeout eventually terminated it and returned status 124. Adding:

```text
-action shutdown=poweroff
```

did not change that behavior.

Because the runner stops on the first nonzero result, the following cases
were not completed:

- 2-vCPU PLIC
- 8-vCPU PLIC
- virtio block
- virtio user networking
- AIA with APLIC/IMSIC

## Comparison with earlier KVM testing

The SSTC, Svpbmt, and Zicboz compatibility problems were previously observed
on the older Omni 7.1.5 control kernel.

However, the earlier custom upstream host:

```text
7.3.0-rc4-k3-kvm-host-a1
```

passed the complete eight-case matrix using QEMU 10.2.2:

- compatibility CPU mask: 8/8 passed;
- plain `-cpu host`: 8/8 passed;
- 1, 2, and 8 vCPUs passed;
- PLIC and AIA passed;
- virtio block and networking passed; and
- QEMU exited normally after guest poweroff.

Therefore, the current failures are not inherent to the smoke guest. They
appear to involve the current COPR host kernel, Fedora's QEMU 11.1 RC3 build,
or their interaction.

## Current assessment

| Area | Result |
| --- | --- |
| Fedora 45 boot | PASS |
| NVMe root and `/boot` | PASS |
| General host stability | PASS |
| K3 thermal sensor | PASS |
| CTF2301 kernel fan control | PASS |
| Native KVM guest launch | PASS |
| One-vCPU PLIC delivery with compatibility mask | PASS |
| Unmasked SSTC guest execution | FAIL |
| Clean QEMU exit after guest poweroff | FAIL |
| Complete KVM matrix | NOT RUN |

## Suggested follow-up

1. Run the current `7.3.0-65.1` host with the previously validated QEMU
   10.2.2 build to separate a QEMU regression from a host-kernel regression.
2. Test QEMU 11.1 on the earlier `7.3.0-rc4-k3-kvm-host-a1` kernel if that
   kernel remains available.
3. Investigate why KVM exposes SSTC but QEMU reports that it cannot disable
   the extension.
4. Determine why QEMU remains alive after the guest's successful poweroff
   request.
5. Once those issues are resolved, rerun the complete PLIC, SMP, virtio, and
   AIA matrix.
