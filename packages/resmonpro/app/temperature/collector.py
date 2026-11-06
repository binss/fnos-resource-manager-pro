#!/usr/bin/env python3
"""Collect fnOS hwmon temperatures without sudo or third party packages."""
import argparse
import csv
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import socket
import subprocess
from zoneinfo import ZoneInfo

DATA = Path(os.environ.get('TRIM_PKGVAR', str(Path.home() / '.local/share/thermoboard')))
TZ = ZoneInfo('Asia/Shanghai')


def read(path, default=None):
    try:
        return path.read_text().strip()
    except OSError:
        return default


def celsius(path):
    value = read(path)
    try:
        value = float(value) / 1000
        return round(value, 3) if -30 <= value <= 150 else None
    except (ValueError, TypeError):
        return None


def atomic_json(path, value):
    tmp = path.with_name(path.name + '.new')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    os.replace(tmp, path)


def measure():
    now = dt.datetime.now(TZ)
    inventory = json.loads(subprocess.check_output(
        ['lsblk', '-J', '-d', '-o', 'NAME,MODEL,SERIAL,TRAN'], text=True, timeout=10
    ))['blockdevices']
    disks = []
    for disk in inventory:
        if disk.get('tran') not in ('sata', 'nvme', 'sas', 'usb'):
            continue
        disk['sys_path'] = str((Path('/sys/class/block') / disk['name']).resolve())
        disks.append(disk)
    readings, errors = [], []
    seen_disks = set()
    for hw in sorted(Path('/sys/class/hwmon').glob('hwmon*')):
        chip = read(hw / 'name', hw.name)
        device_path = str((hw / 'device').resolve())
        disk = next((d for d in disks if d['sys_path'].startswith(device_path + '/')), None)
        for sensor in sorted(hw.glob('temp*_input')):
            stem = sensor.name.removesuffix('_input')
            value = celsius(sensor)
            if value is None:
                errors.append({'source': str(sensor), 'error': 'temperature unavailable or invalid'})
                continue
            label = read(hw / (stem + '_label'), stem)
            if disk:
                kind = 'disk'
                identity = disk.get('serial') or disk['sys_path']
                model = (disk.get('model') or '').strip()
                name = disk['name']
                primary = label == 'Composite' if chip == 'nvme' else stem == 'temp1'
                if primary:
                    seen_disks.add(name)
            else:
                kind = {
                    'k10temp': 'cpu', 'coretemp': 'cpu', 'amdgpu': 'gpu',
                    'spd5118': 'memory', 'acpitz': 'acpi', 'mt7921_phy0': 'network',
                }.get(chip, 'network' if chip.startswith('r8169') else 'other')
                identity = device_path
                model, name, primary = chip, chip, True
            flags = {
                suffix: read(hw / (stem + '_' + suffix))
                for suffix in ('alarm', 'crit_alarm', 'max_alarm')
            }
            critical = celsius(hw / (stem + '_crit'))
            readings.append({
                'key': kind + ':' + identity + ':' + label,
                'kind': kind, 'device': name, 'model': model,
                'serial': disk.get('serial') if disk else None,
                'sensor': label, 'temperature_c': value, 'primary': primary,
                'critical_c': critical, 'max_c': celsius(hw / (stem + '_max')),
                'hardware_alarm': any(v == '1' for v in flags.values()),
                'at_critical': critical is not None and value >= critical,
                'source': str(sensor),
            })
    for disk in disks:
        if disk['name'] not in seen_disks:
            errors.append({'device': disk['name'], 'model': disk.get('model'),
                           'error': 'no readable primary disk temperature'})
    return {'timestamp': now.isoformat(timespec='seconds'), 'date': now.date().isoformat(),
            'host': socket.gethostname(), 'disks': disks, 'readings': readings, 'errors': errors}


def collect():
    os.umask(0o077)
    DATA.mkdir(parents=True, exist_ok=True)
    with (DATA / '.collect.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        sample = measure()
        day = sample['date']
        raw_path = DATA / (day + '.jsonl')
        with raw_path.open('a') as out:
            out.write(json.dumps(sample, ensure_ascii=False) + '\n')
        csv_path = DATA / (day + '.csv')
        fields = ['timestamp', 'kind', 'device', 'model', 'serial', 'sensor',
                  'temperature_c', 'primary', 'critical_c', 'max_c', 'hardware_alarm']
        new = not csv_path.exists() or csv_path.stat().st_size == 0
        with csv_path.open('a', newline='') as out:
            writer = csv.DictWriter(out, fieldnames=fields, extrasaction='ignore')
            if new:
                writer.writeheader()
            for row in sample['readings']:
                writer.writerow({'timestamp': sample['timestamp'], **row})
        samples = [json.loads(line) for line in raw_path.read_text().splitlines() if line]
        groups = {}
        for item in samples:
            for row in item['readings']:
                groups.setdefault(row['key'], []).append((item['timestamp'], row))
        stats = []
        for key, rows in groups.items():
            last = rows[-1][1]
            values = [r['temperature_c'] for _, r in rows]
            stats.append({k: last[k] for k in ('key', 'kind', 'device', 'model', 'serial', 'sensor', 'primary')})
            stats[-1].update(count=len(values), minimum_c=min(values), maximum_c=max(values),
                             average_c=round(sum(values) / len(values), 2),
                             latest_c=values[-1], latest_at=rows[-1][0])
        summary = {'date': day, 'samples': len(samples), 'first_at': samples[0]['timestamp'],
                   'last_at': samples[-1]['timestamp'], 'statistics': stats}
        atomic_json(DATA / ('summary-' + day + '.json'), summary)
        atomic_json(DATA / 'latest.json', sample)
        print(json.dumps({'sample': sample, 'summary': summary}, ensure_ascii=False))


def report():
    latest = json.loads((DATA / 'latest.json').read_text())
    summary = json.loads((DATA / ('summary-' + latest['date'] + '.json')).read_text())
    print(json.dumps({'sample': latest, 'summary': summary}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['collect', 'report'])
    args = parser.parse_args()
    collect() if args.action == 'collect' else report()
