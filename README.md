# K3-CoM260 notes and tools

A collection of what I learn and do with the **SpacemiT K3-CoM260**:
board notes, hardware findings, firmware and OS bring-up, recovery procedures,
and assorted tools, scripts, and patches.

This is an evolving resource for sharing practical work with the board,
rather than a single software project.

## Documentation and tools

**Start with the [Fedora developer wiki](https://github.com/xjamesmorris/k3-com260-info/wiki).**
It is the primary entry point for the recorded Fedora/NVMe route, hardware
setup, maintenance, diagnostics, kernel and device-tree work, virtualization,
and upstream contribution. The canonical source lives in
[`wiki/`](wiki/Home.md); its [maintenance tools](tools/wiki/README.md) validate
the separate GitHub Wiki projection. Editing or pushing this repository does
not itself publish the wiki.

The focused standalone documents and tools remain available:

- [Fedora 44 and KVM how-to](k3-com260-fedora-howto/README.md): a standalone
  guide to bootstrapping Fedora on NVMe with stock Bianbu/U-Boot, building and
  installing a pinned KVM host kernel, and running a persistent Fedora guest.
  It preserves the recorded bring-up and includes helper scripts and the
  [kernel configuration and 14-patch bundle](k3-com260-fedora-howto/files/kernel/README.md).
- [Tools](tools/README.md): currently a Bianbu factory-flashing script using
  stock `fastboot`, with usage, recovery instructions, and recorded results.
- [Flashing development context](tools/k3-flash-bianbu-HANDOFF.md): protocol
  findings, design decisions, and ideas for further work.

The Fedora how-to remains the focused bring-up record highlighted by the wiki.
Its directory in this repository is `k3-com260-fedora-howto/`; after setting
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

The Fedora how-to records a **September 25, 2026 bring-up snapshot** with
Bianbu Minimal K3 v4.0.1 non-UEFI firmware. Its historical stages ran on
hardware, but the portable bundle has not been rerun end to end; newer
images, kernels, and toolchains are not validated substitutions.

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
