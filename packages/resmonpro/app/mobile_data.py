"""Read-only system views for the standalone app-gateway frontend.

Only names, counters and resource metrics are returned. Process command lines,
environments, credentials and disk serial numbers are never collected here.
"""
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import subprocess
import time

from monitor import live, recent, gpu_live

PROC = Path('/proc')
STATE = Path('/var/apps/resmonpro/var/mobile-counters.json')


def process_snapshot(proc=PROC):
    result = []
    hz = os.sysconf('SC_CLK_TCK')
    page = os.sysconf('SC_PAGE_SIZE')
    for directory in proc.glob('[0-9]*'):
        try:
            stat = (directory / 'stat').read_text()
            end = stat.rindex(')')
            fields = stat[end + 2:].split()
            name = stat[stat.index('(') + 1:end]
            ticks = int(fields[11]) + int(fields[12])
            group = '系统'
            try:
                cgroup = (directory / 'cgroup').read_text()
                units = re.findall(r'/([^/\n]+\.service)(?:/|$)', cgroup)
                if units:
                    group = units[-1].removesuffix('.service')
            except OSError:
                pass
            result.append({'pid':int(directory.name), 'name':name, 'state':fields[0],
                           'ticks':ticks, 'start':int(fields[19]),
                           'cpu_time':ticks / hz, 'memory':max(0,int(fields[21])) * page,
                           'group':group})
        except (OSError, ValueError, IndexError):
            continue  # Processes may exit between directory enumeration and read.
    return result


def disk_counters(proc=PROC):
    result = {}
    try:
        for line in (proc / 'diskstats').read_text().splitlines():
            fields = line.split()
            if len(fields) >= 14:
                result[fields[2]] = [int(fields[5])*512,int(fields[9])*512,int(fields[12])]
    except (OSError, ValueError):
        pass
    return result


def sample():
    now = time.monotonic()
    boot = (PROC / 'sys/kernel/random/boot_id').read_text().strip()
    processes = process_snapshot()
    disks = disk_counters()
    previous = {}
    try:
        previous = json.loads(STATE.read_text())
    except (OSError, ValueError):
        pass
    elapsed = now - previous.get('time',now)
    valid = previous.get('boot') == boot and 0.1 <= elapsed <= 30
    before = previous.get('processes',{}) if valid else {}
    hz = os.sysconf('SC_CLK_TCK')
    for row in processes:
        old = before.get(str(row['pid']))
        row['cpu'] = max(0,(row['ticks']-old[0])/hz/elapsed*100) if old and old[1] == row['start'] and row['ticks'] >= old[0] else None
    disk_rates = {}
    for name,counters in disks.items():
        old = previous.get('disks',{}).get(name) if valid else None
        if old and all(a >= b for a,b in zip(counters,old)):
            disk_rates[name] = {'read':(counters[0]-old[0])/elapsed,'write':(counters[1]-old[1])/elapsed,
                                'busy':min(100,(counters[2]-old[2])/elapsed/10)}
    # A tiny package-owned counter cache, never a credential store or history DB.
    STATE.parent.mkdir(parents=True,exist_ok=True)
    temporary = STATE.with_name(STATE.name+'.'+str(os.getpid()))
    try:
        temporary.write_text(json.dumps({'time':now,'boot':boot,'disks':disks,
            'processes':{str(p['pid']):[p['ticks'],p['start']] for p in processes}}))
        temporary.chmod(0o600)
        temporary.replace(STATE)
    finally:
        temporary.unlink(missing_ok=True)
    for row in processes:
        row.pop('ticks');row.pop('start')
    return processes,disk_rates


def disk_inventory(rates):
    try:
        data = json.loads(subprocess.check_output(['lsblk','--json','--bytes','--nodeps','--output','NAME,TYPE,SIZE,MODEL'],timeout=4,text=True))
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    return [{'name':d['name'],'model':(d.get('model') or d['name']).strip(),'size':d.get('size'),
             **rates.get(d['name'],{'read':None,'write':None,'busy':None})}
            for d in data.get('blockdevices',[]) if d.get('type') == 'disk' and not re.match(r'^(loop|ram|zram)',d['name'])]


def summary():
    processes,rates = sample()
    resources = live()
    try:
        history = recent()
    except (OSError, sqlite3.Error):
        history = {}
    latest = history.get('latest')
    resources['cpu'] = latest[1] if latest else None
    resources['cpu_user'] = latest[4] if latest and len(latest)>4 else None
    resources['cpu_system'] = latest[5] if latest and len(latest)>5 else None
    resources['cpu_iowait'] = latest[6] if latest and len(latest)>6 else None
    uptime = float((PROC / 'uptime').read_text().split()[0])
    networks = [{'name':n['name'],'receive':n['points'][-1][1] if n['points'] else None,
                 'transmit':n['points'][-1][2] if n['points'] else None} for n in history.get('networks',[])]
    fans=[]
    for hw in Path('/sys/class/hwmon').glob('hwmon*'):
        for sensor in hw.glob('fan*_input'):
            try:
                rpm=int(sensor.read_text());
                if rpm>0:fans.append(rpm)
            except (OSError,ValueError):pass
    return {'resources':resources,'host':socket.gethostname(),'uptime':uptime,'networks':networks,
            'gpus':gpu_live(),'disks':disk_inventory(rates),'processes':processes,'fans':fans}
