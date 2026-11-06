"""Read DRM engine counters only; publish aggregate GPU utilization, never process data."""
import json
import os
from pathlib import Path
import time

OUTPUT = Path('/run/resmonpro-gpu/engines.json')

def counters():
    clients = {}
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            descriptors = list((proc / 'fd').iterdir())
        except OSError:
            continue
        for fd in descriptors:
            try:
                if not os.readlink(fd).startswith('/dev/dri/'):
                    continue
                fields = dict(line.split(':', 1) for line in (proc / 'fdinfo' / fd.name).read_text().splitlines() if ':' in line)
                pci = fields.get('drm-pdev', '').strip()
                client = fields.get('drm-client-id', '').strip()
                if not pci or not client or (pci, client) in clients:
                    continue
                engines = {}
                for key, value in fields.items():
                    if key.startswith('drm-engine-') and not key.startswith('drm-engine-capacity-') and value.strip().endswith(' ns'):
                        name = key.removeprefix('drm-engine-')
                        capacity = int(fields.get('drm-engine-capacity-' + name, '1').split()[0])
                        engines[name] = (int(value.split()[0]), max(1, capacity))
                clients[pci, client] = engines
            except (OSError, ValueError):
                continue
    return clients


def run():
    previous = None
    last = time.monotonic_ns()
    while Path('/var/apps/resmonpro/target').exists():
        if not Path('/var/apps/resmonpro/var/app.pid').exists():
            previous = None
            time.sleep(3)
            continue
        current = counters()
        now = time.monotonic_ns()
        by_pci = {}
        for device in Path('/sys/class/drm').glob('card[0-9]*'):
            if not device.name[4:].isdigit() or not (device / 'device').exists():
                continue
            try:
                if (device / 'device/driver').resolve(strict=True).name != 'amdgpu':
                    continue
            except OSError:
                continue
            pci = (device / 'device').resolve().name
            by_pci[pci] = {'compute': None if previous is None else 0.0, 'encoder': None if previous is None else 0.0}
        if previous is not None:
            for client, engines in current.items():
                total = by_pci.get(client[0])
                if total is None:
                    continue
                for engine, (ticks, capacity) in engines.items():
                    kind = 'compute' if engine == 'compute' else 'encoder' if engine.startswith('enc') else None
                    if kind is None:
                        continue
                    old = previous.get(client, {}).get(engine)
                    if old is None:
                        total[kind] = None
                    elif total[kind] is not None and ticks >= old[0]:
                        total[kind] += 100 * (ticks - old[0]) / (now - last) / capacity
                    else:
                        total[kind] = None
        payload = {'ts': int(time.time()), 'devices': {pci:{name:None if value is None else round(min(100,value),2) for name,value in engines.items()} for pci,engines in by_pci.items()}}
        temporary = OUTPUT.with_suffix('.tmp')
        temporary.write_text(json.dumps(payload))
        temporary.chmod(0o644)
        temporary.replace(OUTPUT)
        previous, last = current, now
        time.sleep(max(.1, 3 - time.time() % 3))

if __name__ == '__main__':
    run()
