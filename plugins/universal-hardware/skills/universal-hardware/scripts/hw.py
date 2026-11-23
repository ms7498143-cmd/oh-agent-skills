#!/usr/bin/env python3
"""Universal hardware profile editor.

  hw.py set cpu.count=50 cpu.brand="AMD EPYC 9B14" memory.size=256g
  hw.py add-device '{"type":"gpu","brand":"NVIDIA","model":"H100","count":8}'
  hw.py show
  hw.py view
  hw.py apply cpus=4 memory=12g runtime=docker
  hw.py physical
"""
import json, os, sys

H = os.path.expanduser("~/.openhands/hardware.json")
V = os.path.expanduser("~/.openhands/hardware/bin")


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
        return
    print(__doc__)


main()
