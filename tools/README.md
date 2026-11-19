<!-- SPDX-License-Identifier: GPL-2.0-only -->

# K3-CoM260 tools have moved

The Bianbu factory-flashing script and k3ctl moved to
**[k3-tools](https://github.com/xjamesmorris/k3-tools)** on 2026-11-19, with
their history:

- [k3-flash-bianbu](https://github.com/xjamesmorris/k3-tools/blob/main/k3-flash-bianbu/README.md):
  factory flashing with stock `fastboot`, including
  [putting the board in recovery](https://github.com/xjamesmorris/k3-tools/blob/main/k3-flash-bianbu/README.md#putting-the-board-in-recovery)
  and the [recorded image results](https://github.com/xjamesmorris/k3-tools/blob/main/k3-flash-bianbu/README.md#status).
  **Factory flashing erases NOR firmware and all UFS contents.**
- [k3ctl](https://github.com/xjamesmorris/k3-tools/blob/main/k3ctl/README.md):
  USB header-button control for the K3-CoM260 on the Firefly carrier.

The last version of these tools in this repository is at commit
[`7e8c58f`](https://github.com/xjamesmorris/k3-com260-info/tree/7e8c58f1308b822c857204ba600238e9699e3947/tools),
where older links to sections of this page still resolve.

The [wiki tools](wiki/README.md) in this directory stay here: they validate
and publish this repository's wiki.
