---
name: universal-hardware
description: Declare and apply arbitrary hardware profiles for an OpenHands workspace — any CPU count or brand, memory size, and any GPUs, NPUs, NICs, storage, or custom devices with any brand/model/count. Boots a persistent lifetime QEMU guest with guest-physical CPU/RAM, networking, SSH, and a durable disk. No declared ceiling. Use when asked to change VM/workspace hardware, add devices, set CPU or memory limits, run work inside the guest, or build a virtual hardware view.
---

# Universal hardware profile

The declared profile lives in `~/.openhands/hardware.json`. Values have **no software ceiling** — any count, brand, model, or device type. QEMU and the host's physical resources still bound what can actually run; the skill never adds its own cap.

## Lifetime QEMU workspace

`bootstrap` runs automatically on session start (plugin hook). It:

1. writes the profile (default **50 CPU / 150 GB / 3 GPU / 3 NPU**),
2. installs the prebuilt Alpine disk to `/workspace/.qemu-lifetime/alpine/disk.img` if absent,
3. starts a **supervised** QEMU guest that restarts itself if it ever exits.

The disk lives on the `/workspace` volume, so packages, files, and servers survive conversation close and workspace restart. On a brand-new workspace the prebuilt image is restored automatically. A full container rebuild cannot preserve in-guest changes; the shipped image gives you a ready system again.

Boot is not instant on this host: there is no `/dev/kvm`, so QEMU runs in TCG mode and a cold boot takes roughly 90-140 s. The VM is kept running (lifetime), so you normally never wait for boot. Idle host CPU is about 0.03 of one core when the guest is idle.

### Everyday commands

```bash
python3 scripts/hw.py bootstrap          # profile + install disk + start guest
python3 scripts/hw.py vm-ensure          # start if not already running
python3 scripts/hw.py vm-status          # host, mode, disk, pid, boot markers
python3 scripts/hw.py gexec 'uname -a'   # run a command inside the guest (serial socket)
python3 scripts/hw.py ssh-setup          # install this workspace's key into the guest
python3 scripts/hw.py ssh 'nproc; df -h' # run over SSH (127.0.0.1:2222)
```

`gexec` is the always-available channel: it talks to the guest's second serial port over a Unix socket, so it works even before SSH is configured.

## Set declared hardware

```bash
python3 scripts/hw.py set cpu.count=50 cpu.brand="AMD EPYC 9B14" memory.size=150g
python3 scripts/hw.py add-device '{"type":"gpu","brand":"QEMU","model":"virtio-gpu-pci","count":3,"emulate":"virtio-gpu-pci"}'
python3 scripts/hw.py add-device '{"type":"npu","brand":"QEMU","model":"pci-testdev","count":3,"emulate":"pci-testdev"}'
python3 scripts/hw.py show
```

Any device type is allowed: `gpu`, `npu`, `tpu`, `nic`, `storage`, `fpga`, or custom. A device with `"emulate": "<qemu -device>"` is attached to the guest at that count. Brand and model are labels; the guest sees the QEMU model you choose.

## Virtual view (what programs inside see)

```bash
python3 scripts/hw.py view
export PATH="$HOME/.openhands/hardware/bin:$PATH"
nproc
cat "$HOME/.openhands/hardware/bin/cpuinfo"
```

## Real container limits

```bash
python3 scripts/hw.py apply cpus=4 memory=12g runtime=docker
```

Calls `POST /api/v1/settings`. The platform may cap the real container; the QEMU guest still honors the manifest.

## Host footprint

- No KVM here: TCG emulation. More vCPUs/memory do not consume host CPU when the guest is idle, but they cost boot time and host RAM for touched pages.
- The guest disk is sparse (16 GiB apparent, ~260 MB on disk).
- The supervisor restarts QEMU within ~5 s if it exits.

## Requirements

`qemu-system-x86`, `e2fsprogs` (mkfs/debugfs), `gzip`, `cpio`, `openssh-client`. `hw.py vm-install` installs the first two with apt.
