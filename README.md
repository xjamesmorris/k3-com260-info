# K3-CoM260 notes and tools

A collection of what I learn and do with the **SpacemiT K3-CoM260**:
board notes, hardware findings, firmware and OS bring-up, recovery procedures,
and assorted tools, scripts, and patches.

This is an evolving resource for sharing practical work with the board,
rather than a single software project.

## Documentation and tools

- [Tools](tools/README.md): currently a Bianbu factory-flashing script using
  stock `fastboot`, with usage, recovery instructions, and recorded results.
- [Flashing development context](tools/k3-flash-bianbu-HANDOFF.md): protocol
  findings, design decisions, and ideas for further work.

A GitHub wiki is planned for longer-form board documentation and notes.
More scripts and patches will be added as the work develops.

## Hardware and results

The existing flashing work was done with a **K3-CoM260 on a Firefly carrier**.
Carrier-specific wiring and procedures may not apply to other setups.
The tool documentation distinguishes image checksums pinned in the manifest
from actual flash and boot results.

**Factory flashing erases NOR firmware and all UFS contents.** Read the
[tool documentation](tools/README.md) before using the script.

## Contributing

Corrections, patches, and additional hardware results are welcome. Include
the module, carrier, relevant firmware or OS versions, and what you tried.
For patches, identify the target project and revision.

## License

GPL-2.0-only. See [LICENSE](LICENSE).
