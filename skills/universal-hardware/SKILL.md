---
name: universal-hardware
description: Declare and apply arbitrary hardware profiles for an OpenHands workspace — any CPU count or brand, memory size, and any GPUs, NPUs, NICs, storage, or custom devices with any brand/model/count. Boots a real QEMU guest with guest-physical CPU/RAM. No declared ceiling. Use when asked to change VM/workspace hardware, add devices, set CPU or memory limits, or build a virtual hardware view.
---

# Universal hardware profile

`scripts/hw.py` edits `~/.openhands/hardware.json`. Declared values have **no ceiling** — any count, brand, model, or device type.

## Set declared hardware

```bash
python3 scripts/hw.py set cpu.count=50 cpu.brand="AMD EPYC 9B14" memory.size=256g
python3 scripts/hw.py add-device '{"type":"gpu","brand":"NVIDIA","model":"H100","count":8,"memory":"80g"}'
python3 scripts/hw.py add-device '{"type":"npu","brand":"Qualcomm","model":"Hexagon","count":2}'
python3 scripts/hw.py show
```

Any device type is allowed: `gpu`, `npu`, `tpu`, `nic`, `storage`, `fpga`, or custom.

## Virtual view (what programs inside see)

```bash
python3 scripts/hw.py view
export PATH="$HOME/.openhands/hardware/bin:$PATH"
nproc
cat "$HOME/.openhands/hardware/bin/cpuinfo"
```

## Real container limits (capped by the machine)

```bash
python3 scripts/hw.py apply cpus=4 memory=12g runtime=docker
```

This calls `POST /api/v1/settings` with `conversation_settings_diff`. The platform caps `container_cpus` at the machine's CPU count, and the limits apply to **new Docker-runtime conversations**. A running local sandbox is not resized.

## Physical VM layer (real guest hardware)

`bootstrap` boots a real QEMU guest with the declared CPU count and RAM. The guest sees them as physical:

```bash
python3 scripts/hw.py vm-install   # apt install qemu-system-x86 busybox-static (sudo)
python3 scripts/hw.py vm-build     # download Alpine kernel + build initramfs
python3 scripts/hw.py vm-plan      # write ~/.openhands/hardware/vm/run.sh
python3 scripts/hw.py vm-up        # boot detached, log ~/.openhands/hardware/vm/boot.log
python3 scripts/hw.py vm-status    # guest vs host, accel, pid
```

Verified on this host:

```
guest_nproc=50
guest_cpu_lines=50
MemTotal: 263929300 kB   # 251.7 GiB guest-visible
host_nproc 4
host_MemTotal: 16374236 kB
accel tcg (no /dev/kvm)
```

The guest's CPU and RAM are real to processes inside it. The host still backs them: 50 vCPUs are time-sliced on 4 physical cores, and 256 GiB is overcommitted on 15.6 GiB. GPUs/NPUs are declared, not passed through; no physical H100 or NPU exists.

## Physical truth

```bash
python3 scripts/hw.py physical
```

Three layers: declared manifest, guest-physical VM (`vm-status`), and host-backed substrate (`physical`). Report all three. Never claim a declared GPU/NPU is physical silicon.

## Startup (forced on workspace open)

`.openhands/hooks.json` runs `hw.py bootstrap` on `session_start`, so every new session starts with the high-spec profile already applied:

```bash
python3 .agents/skills/universal-hardware/scripts/hw.py bootstrap
```

It sets 50 CPUs (AMD EPYC 9B14), 256g, 8×H100, 2×Hexagon NPU, writes the virtual view, autostarts the QEMU guest unless `HW_VM_AUTOSTART=0`, and is idempotent. Override with `HW_CPU_COUNT`, `HW_CPU_BRAND`, or `HW_MEMORY`.

Marketplace-loaded workspaces use the plugin hook `hooks/hooks.json` with `$PLUGIN_ROOT`.

## Mars integration

The Mars runtime exposes `/api/world` (hostname, PID 1, cgroup, engine inside) and `/api/physics` (declared vs achieved).
