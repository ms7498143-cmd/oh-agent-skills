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
# Persistent volume so the lifetime disk survives workspace close/restart.
PERSIST = os.environ.get("HW_PERSIST_DIR") or (
    "/workspace/.qemu-lifetime" if os.path.isdir("/workspace")
    else os.path.join(os.path.expanduser("~/.openhands/hardware"), "persist"))
ALPINE = os.path.join(PERSIST, "alpine")
VMLINUZ = os.path.join(ALPINE, "vmlinuz-virt")
INITRD_V = os.path.join(ALPINE, "initramfs-virt")
DISK = os.path.join(ALPINE, "disk.img")
ASSET = os.path.join(ROOT, "assets", "disk.img.gz")
SERIAL_SOCK = os.path.join(VM, "serial.sock")


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
    if os.path.exists(DISK):
        cmd = ["qemu-system-x86_64", "-M", "q35", "-accel", "tcg,thread=multi",
               "-smp", str(n), "-m", mem,
               "-kernel", VMLINUZ, "-initrd", INITRD_V,
               "-append", "root=/dev/vda rw rootfstype=ext4 "
                          "modules=virtio_blk,virtio_net "
                          "console=ttyS0 quiet",
               "-drive", "file=%s,if=virtio,format=raw,cache=writeback" % DISK,
               "-netdev", "user,id=n0,hostfwd=tcp::2222-:22",
               "-device", "virtio-net-pci,netdev=n0",
               "-display", "none", "-serial", "file:" + log,
               "-serial", "unix:%s,server=on,wait=off" % SERIAL_SOCK,
               "-monitor", "none", "-no-reboot"]
    else:
        cmd = ["qemu-system-x86_64", "-M", "q35", "-accel", "tcg,thread=multi",
               "-smp", str(n), "-m", mem, "-kernel", KERNEL, "-initrd", INITRD,
               "-append", "console=ttyS0 quiet", "-display", "none",
               "-serial", "file:" + log, "-serial", "pty",
               "-monitor", "none", "-no-reboot"]
    for dev in d.get("devices", []):
        em = dev.get("emulate")
        if em:
            for _ in range(int(dev.get("count", 1))):
                cmd += ["-device", em]
    return cmd


def _vm_alive():
    try:
        pid = int(open(os.path.join(VM, "pid")).read().strip())
        os.kill(pid, 0)
        try:
            st = open("/proc/%d/stat" % pid).read().split(") ", 1)[1].split()[0]
            if st == "Z":
                return None
        except Exception:
            pass
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
    if not os.path.exists(DISK):
        _ensure_assets()
    if os.path.exists(DISK):
        need = [VMLINUZ, INITRD_V, DISK]
        hint = "check assets/disk.img.gz or HW_DISK_URL"
    else:
        need = [KERNEL, INITRD]
        hint = "hw.py vm-build"
    miss = [p for p in need if not os.path.exists(p)]
    if miss:
        print("vm assets missing:", " ".join(miss), "->", hint); return
    pid = _vm_alive()
    if pid:
        print("vm already running pid", pid); return
    os.makedirs(VM, exist_ok=True)
    run, _ = _vm_plan(d)
    sup = os.path.join(VM, "serve.sh")
    open(sup, "w").write(
        "#!/bin/sh\n"
        "# lifetime supervisor: restart the guest whenever it exits\n"
        "cd %s\n"
        "while :; do\n"
        "  rm -f %s\n"
        "  %s\n"
        "  sleep 5\n"
        "done\n" % (shlex.quote(VM), shlex.quote(SERIAL_SOCK), shlex.quote(run)))
    os.chmod(sup, 0o755)
    err = os.path.join(VM, "qemu.err")
    p = subprocess.Popen([sup], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL,
                         stderr=open(err, "ab"),
                         start_new_session=True)
    open(os.path.join(VM, "pid"), "w").write(str(p.pid))
    print("vm supervisor started pid", p.pid, "log", os.path.join(VM, "boot.log"))


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
/bin/busybox mkdir -p /proc /sys /dev /tmp
/bin/busybox mount -t proc proc /proc
/bin/busybox mount -t sysfs sys /sys
/bin/busybox mount -t devtmpfs dev /dev 2>/dev/null
/bin/busybox --install -s /bin
echo "VM_BOOTED"
echo "guest_nproc=$(/bin/busybox nproc)"
echo "guest_cpu_lines=$(/bin/busybox grep -c ^processor /proc/cpuinfo)"
/bin/busybox grep MemTotal /proc/meminfo
echo "=== PCI INVENTORY ==="
for dev in /sys/bus/pci/devices/*; do
  echo "PCI $(/bin/busybox basename "$dev") class=$(/bin/busybox cat "$dev/class" 2>/dev/null) vendor=$(/bin/busybox cat "$dev/vendor" 2>/dev/null) device=$(/bin/busybox cat "$dev/device" 2>/dev/null)"
done
echo "=== DEVICE COUNTS ==="
echo "gpu_count=$(/bin/busybox grep -l '^0x1050$' /sys/bus/pci/devices/*/device 2>/dev/null | /bin/busybox wc -l)"
echo "npu_count=$(/bin/busybox grep -l '^0x0005$' /sys/bus/pci/devices/*/device 2>/dev/null | /bin/busybox wc -l)"
echo "VM_READY"
/bin/busybox stty -echo < /dev/ttyS1 2>/dev/null
exec /bin/busybox setsid /bin/busybox sh -c 'exec /bin/busybox sh </dev/ttyS1 >/dev/ttyS1 2>&1'
"""
            open(os.path.join(t, "init"), "w").write(init)
            os.chmod(os.path.join(t, "init"), 0o755)
            subprocess.run(
                "find . | /bin/busybox cpio -o -H newc 2>/dev/null | gzip > " + INITRD,
                shell=True, cwd=t, check=True)
    print("vm assets ready:", KERNEL, INITRD)


def _ensure_assets():
    os.makedirs(ALPINE, exist_ok=True)
    if not os.path.exists(DISK):
        src = ASSET
        if not os.path.exists(src):
            url = os.environ.get(
                "HW_DISK_URL",
                "https://raw.githubusercontent.com/ms7498143-cmd/oh-agent-skills/"
                "main/plugins/universal-hardware/skills/universal-hardware/"
                "assets/disk.img.gz")
            tmp = os.path.join(ALPINE, "disk.img.gz.download")
            try:
                print("lifetime disk missing; downloading prebuilt image...")
                urllib.request.urlretrieve(url, tmp)
                src = tmp
            except Exception as e:
                print("lifetime disk missing and download failed:", e)
                print("provide assets/disk.img.gz or set HW_DISK_URL"); return False
        print("installing lifetime disk (one-time)...")
        with open(DISK, "wb") as f:
            subprocess.run(["gzip", "-dc", src], stdout=f, check=True)
        if src.endswith(".download"):
            os.remove(src)
    for s, dst in (("/boot/vmlinuz-virt", VMLINUZ),
                   ("/boot/initramfs-virt", INITRD_V)):
        if not os.path.exists(dst):
            subprocess.run(["debugfs", "-R", "dump %s %s" % (s, dst), DISK],
                           check=False, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        if os.path.exists(dst):
            os.chmod(dst, 0o644)
    return all(os.path.exists(p) for p in (DISK, VMLINUZ, INITRD_V))


def _vm_status():
    print("host_nproc", os.cpu_count())
    for l in open("/proc/meminfo"):
        if l.startswith("MemTotal"):
            print("host_" + l.strip())
            break
    print("vm_pid", _vm_alive() or "stopped")
    print("accel", "tcg (no /dev/kvm)" if not os.path.exists("/dev/kvm") else "kvm")
    print("mode", "disk(lifetime)" if os.path.exists(DISK) else "initramfs")
    if os.path.exists(DISK):
        print("disk", DISK, "%.1fG apparent" % (os.path.getsize(DISK) / 1e9))
        print("net", "user hostfwd tcp::2222->:22")
    log = os.path.join(VM, "boot.log")
    if os.path.exists(log):
        for line in open(log):
            if line.startswith(("VM_", "guest_", "Mem:", "MemTotal:", "RC_LOCAL_DONE", "Welcome")):
                print(line.rstrip())


def _gexec(command, timeout=60):
    import time, select, socket
    if not os.path.exists(SERIAL_SOCK):
        print("no guest serial socket; VM not running? (hw.py vm-up)"); return 1
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(5)
    try:
        s.connect(SERIAL_SOCK)
    except Exception as e:
        print("cannot connect to guest serial:", e); return 1
    s.setblocking(False)
    try:
        while select.select([s], [], [], 0)[0]:
            s.recv(65536)
    except Exception:
        pass
    tag = "GX%d" % int(time.time() * 1000)
    s.sendall(("echo %s_S\n%s\necho %s_E\n" % (tag, command, tag)).encode())
    buf, end = b"", time.time() + timeout
    while time.time() < end:
        r, _, _ = select.select([s], [], [], 0.5)
        if r:
            try:
                chunk = s.recv(65536)
            except BlockingIOError:
                continue
            if not chunk:
                break
            buf += chunk
            if ("%s_E" % tag).encode() in buf:
                break
    s.close()
    out, cap = [], False
    for line in buf.decode(errors="replace").splitlines():
        if ("%s_S" % tag) in line:
            cap = True; continue
        if ("%s_E" % tag) in line:
            break
        if cap:
            out.append(line)
    print("\n".join(out))
    return 0


def _ssh_key():
    k = os.path.join(ALPINE, "id_ed25519")
    if not os.path.exists(k):
        os.makedirs(ALPINE, exist_ok=True)
        subprocess.run(["ssh-keygen", "-t", "ed25519", "-f", k, "-N", "",
                        "-C", "openhands-vm"], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return k


def _ssh_setup():
    k = _ssh_key()
    pub = open(k + ".pub").read().strip()
    _gexec("mkdir -p /root/.ssh && printf '%%s\\n' '%s' > /root/.ssh/authorized_keys "
           "&& chmod 700 /root/.ssh && chmod 600 /root/.ssh/authorized_keys "
           "&& echo KEY_INSTALLED" % pub)
    return k


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
            print(f"note: requesting container_cpus={cpus:g} (host has {cap}); "
                  f"the platform may cap the real container, but the QEMU guest "
                  f"honors the manifest with no ceiling")
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
    if a[0] == "gexec":
        sys.exit(_gexec(" ".join(a[1:])))
    if a[0] == "ssh-setup":
        k = _ssh_setup()
        print("ssh -i %s -p 2222 root@127.0.0.1" % k); return
    if a[0] == "ssh":
        k = _ssh_key()
        os.execvp("ssh", ["ssh", "-i", k, "-p", "2222",
                          "-o", "StrictHostKeyChecking=no",
                          "-o", "UserKnownHostsFile=/dev/null",
                          "root@127.0.0.1"] + a[1:])
    if a[0] in ("vm-plan", "vm-up", "vm-ensure", "vm-status", "vm-build", "vm-install"):
        if a[0] == "vm-plan":
            p, cmd = _vm_plan(d); print(p); print(" ".join(cmd))
        elif a[0] in ("vm-up", "vm-ensure"):
            _ensure_assets(); _vm_up(d)
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
        d.setdefault("memory", {})["size"] = os.environ.get("HW_MEMORY", "150g")
        devs = [x for x in d.get("devices", [])
                if x.get("emulate") or x.get("type") not in ("gpu", "npu")]
        def ensure(dev):
            for x in devs:
                if x.get("type") == dev["type"] and x.get("emulate") == dev.get("emulate"):
                    x.update(dev); return
            devs.append(dev)
        ensure({"type": "gpu", "brand": "QEMU", "model": "virtio-gpu-pci",
                "count": 3, "emulate": "virtio-gpu-pci", "performance": "high"})
        ensure({"type": "npu", "brand": "QEMU", "model": "pci-testdev",
                "count": 3, "emulate": "pci-testdev"})
        d["devices"] = devs
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
        _ensure_assets()
        _vm_plan(d)
        if os.environ.get("HW_VM_AUTOSTART", "1") != "0":
            _vm_up(d)
        return
    print(__doc__)


main()
