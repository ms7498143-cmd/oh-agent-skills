#!/usr/bin/env python3
"""Universal hardware profile editor.

  hw.py set cpu.count=50 cpu.brand="AMD EPYC 9B14" memory.size=256g
  hw.py add-device '{"type":"gpu","brand":"NVIDIA","model":"H100","count":8}'
  hw.py show
  hw.py view
  hw.py apply cpus=4 memory=12g runtime=docker
  hw.py physical
"""
import json, os, sys, shlex, shutil, subprocess, tempfile, urllib.request

H = os.path.expanduser("~/.openhands/hardware.json")
V = os.path.expanduser("~/.openhands/hardware/bin")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VM = os.path.expanduser("~/.openhands/hardware/vm")
KERNEL = os.path.join(ROOT, "vm", "vmlinuz-virt")
INITRD = os.path.join(ROOT, "vm", "initramfs.cpio.gz")


def load():
    try:
        return json.load(open(H))
    except Exception:
        return {"cpu": {"count": 1, "brand": "unknown"}, "memory": {"size": "unknown"}, "devices": []}


def save(d):
    os.makedirs(os.path.dirname(H), exist_ok=True)
    json.dump(d, open(H, "w"), indent=2)


def put(d, path, val):
    cur = d
    for k in path[:-1]:
        cur = cur.setdefault(k, {})
    cur[path[-1]] = val


def _mem_qemu(s):
    s = str(s).strip().lower()
    return s[:-1] + s[-1].upper() if s and s[-1] in "gmk" else s


def _vm_cmd(d):
    n = int(d.get("cpu", {}).get("count", 1))
    mem = _mem_qemu(d.get("memory", {}).get("size", "1g"))
    log = os.path.join(VM, "boot.log")
    return ["qemu-system-x86_64", "-M", "q35", "-accel", "tcg,thread=multi",
            "-smp", str(n), "-m", mem, "-kernel", KERNEL, "-initrd", INITRD,
            "-append", "console=ttyS0 quiet", "-display", "none",
            "-serial", "file:" + log, "-monitor", "none", "-no-reboot"]


def _vm_alive():
    try:
        pid = int(open(os.path.join(VM, "pid")).read().strip())
        os.kill(pid, 0)
        return pid
    except Exception:
        return None


def _vm_plan(d):
    os.makedirs(VM, exist_ok=True)
    cmd = _vm_cmd(d)
    p = os.path.join(VM, "run.sh")
    open(p, "w").write("#!/bin/sh\n" + " ".join(shlex.quote(x) for x in cmd) + "\n")
    os.chmod(p, 0o755)
    return p, cmd


def _vm_up(d):
    if not shutil.which("qemu-system-x86_64"):
        print("qemu missing: hw.py vm-install"); return
    if not (os.path.exists(KERNEL) and os.path.exists(INITRD)):
        print("vm assets missing: hw.py vm-build"); return
    pid = _vm_alive()
    if pid:
        print("vm already running pid", pid); return
    os.makedirs(VM, exist_ok=True)
    _, cmd = _vm_plan(d)
    log = os.path.join(VM, "boot.log"); err = os.path.join(VM, "qemu.err")
    open(log, "w").close()
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                         stdout=open(err, "ab"), stderr=subprocess.STDOUT,
                         start_new_session=True)
    open(os.path.join(VM, "pid"), "w").write(str(p.pid))
    print("vm started pid", p.pid, "log", log)


def _vm_build():
    os.makedirs(os.path.join(ROOT, "vm"), exist_ok=True)
    if not os.path.exists(KERNEL):
        urllib.request.urlretrieve(
            "https://dl-cdn.alpinelinux.org/alpine/v3.20/releases/x86_64/netboot/vmlinuz-virt",
            KERNEL)
    if not os.path.exists(INITRD):
        bb = shutil.which("busybox") or "/bin/busybox"
        if not os.path.exists(bb):
            raise SystemExit("busybox missing: apt-get install busybox-static")
        with tempfile.TemporaryDirectory() as t:
            os.makedirs(os.path.join(t, "bin"))
            shutil.copy(bb, os.path.join(t, "bin", "busybox"))
            init = """#!/bin/busybox sh
/bin/busybox mount -t proc proc /proc
/bin/busybox mount -t sysfs sys /sys
/bin/busybox mount -t devtmpfs dev /dev 2>/dev/null
echo "VM_BOOTED"
echo "guest_nproc=$(/bin/busybox nproc)"
echo "guest_cpu_lines=$(/bin/busybox grep -c ^processor /proc/cpuinfo)"
/bin/busybox free -h
/bin/busybox head -3 /proc/meminfo
echo "VM_READY"
/bin/busybox sleep 86400
"""
            open(os.path.join(t, "init"), "w").write(init)
            os.chmod(os.path.join(t, "init"), 0o755)
            subprocess.run(
                "find . | /bin/busybox cpio -o -H newc 2>/dev/null | gzip > " + INITRD,
                shell=True, cwd=t, check=True)
    print("vm assets ready:", KERNEL, INITRD)


def _vm_status():
    print("host_nproc", os.cpu_count())
    for l in open("/proc/meminfo"):
        if l.startswith("MemTotal"):
            print("host_" + l.strip())
            break
    print("vm_pid", _vm_alive() or "stopped")
    print("accel", "tcg (no /dev/kvm)" if not os.path.exists("/dev/kvm") else "kvm")
    log = os.path.join(VM, "boot.log")
    if os.path.exists(log):
        for line in open(log):
            if line.startswith(("VM_", "guest_", "Mem:", "MemTotal:")):
                print(line.rstrip())


def main():
    a = sys.argv[1:]
    if not a or a[0] == "show":
        print(json.dumps(load(), indent=2)); return
    if a[0] == "schema":
        print(json.dumps({"cpu": {"count": "int (no ceiling)", "brand": "str"},
                          "memory": {"size": "str"},
                          "devices": [{"type": "gpu|npu|tpu|nic|storage|fpga|custom",
                                       "brand": "str", "model": "str", "count": "int"}],
                          "network": [], "storage": []}, indent=2)); return
    d = load()
    if a[0] == "set":
        for kv in a[1:]:
            k, v = kv.split("=", 1)
            try:
                v = json.loads(v)
            except Exception:
                pass
            put(d, k.split("."), v)
        save(d); print(json.dumps(d, indent=2)); return
    if a[0] == "add-device":
        d.setdefault("devices", []).append(json.loads(a[1])); save(d)
        print(json.dumps(d, indent=2)); return
    if a[0] == "view":
        os.makedirs(V, exist_ok=True)
        c = d.get("cpu", {}); n = int(c.get("count", 1)); brand = c.get("brand", "unknown")
        with open(os.path.join(V, "cpuinfo"), "w") as f:
            for i in range(n):
                f.write(f"processor\t: {i}\nmodel name\t: {brand}\n\n")
        p = os.path.join(V, "nproc")
        open(p, "w").write(f"#!/bin/sh\necho {n}\n"); os.chmod(p, 0o755)
        print("wrote", os.path.join(V, "cpuinfo"), "and", p)
        print("export PATH=%s:$PATH" % V); return
    if a[0] == "apply":
        cpus = mem = runtime = None
        for kv in a[1:]:
            k, v = kv.split("=", 1)
            if k == "cpus": cpus = float(v)
            elif k == "memory": mem = v
            elif k == "runtime": runtime = v
        cap = os.cpu_count() or 1
        if cpus and cpus > cap:
            print(f"note: container_cpus capped at machine count {cap}"); cpus = cap
        diff = {}
        if cpus is not None: diff["container_cpus"] = cpus
        if mem: diff["container_memory"] = mem
        if runtime: diff["default_runtime"] = runtime
        key = os.environ.get("OPENHANDS_API_KEY")
        if not key:
            print("OPENHANDS_API_KEY not set"); return
        import urllib.request
        req = urllib.request.Request(
            "https://app.all-hands.dev/api/v1/settings",
            data=json.dumps({"conversation_settings_diff": diff}).encode(),
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
            method="POST")
        print(urllib.request.urlopen(req, timeout=15).read().decode()[:500]); return
    if a[0] == "physical":
        print("physical_cores", os.cpu_count())
        for l in open("/proc/meminfo"):
            if l.startswith("MemTotal"):
                print("physical_memory", l.strip())
        return
    if a[0] in ("vm-plan", "vm-up", "vm-status", "vm-build", "vm-install"):
        if a[0] == "vm-plan":
            p, cmd = _vm_plan(d); print(p); print(" ".join(cmd))
        elif a[0] == "vm-up":
            _vm_up(d)
        elif a[0] == "vm-status":
            _vm_status()
        elif a[0] == "vm-build":
            _vm_build()
        else:
            subprocess.run(["sudo", "-n", "apt-get", "install", "-y",
                            "qemu-system-x86", "busybox-static"], check=False)
        return
    if a[0] == "bootstrap":
        d = load()
        d.setdefault("cpu", {}).update({
            "count": int(os.environ.get("HW_CPU_COUNT", "50")),
            "brand": os.environ.get("HW_CPU_BRAND", "AMD EPYC 9B14"),
        })
        d.setdefault("memory", {})["size"] = os.environ.get("HW_MEMORY", "256g")
        devs = d.setdefault("devices", [])
        def ensure(dev):
            if not any(x.get("type") == dev["type"] and x.get("brand") == dev["brand"]
                       and x.get("model") == dev["model"] for x in devs):
                devs.append(dev)
        ensure({"type": "gpu", "brand": "NVIDIA", "model": "H100", "count": 8, "memory": "80g"})
        ensure({"type": "npu", "brand": "Qualcomm", "model": "Hexagon", "count": 2})
        save(d)
        os.makedirs(V, exist_ok=True)
        n = int(d["cpu"]["count"]); brand = d["cpu"]["brand"]
        with open(os.path.join(V, "cpuinfo"), "w") as f:
            for i in range(n):
                f.write(f"processor\t: {i}\nmodel name\t: {brand}\n\n")
        p = os.path.join(V, "nproc")
        open(p, "w").write(f"#!/bin/sh\necho {n}\n"); os.chmod(p, 0o755)
        print(f"universal-hardware bootstrap: {n}x {brand}, {d['memory']['size']}, "
              f"{len(devs)} device types; virtual view {V}")
        _vm_plan(d)
        if os.environ.get("HW_VM_AUTOSTART", "1") != "0":
            _vm_up(d)
        return
    print(__doc__)


main()
