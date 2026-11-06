"""Host resource sampling and bounded history queries."""
from os import cpu_count as os_cpu_count, getloadavg
from pathlib import Path
import json
import sqlite3
import sys
import time
from contextlib import closing

DB = Path("/var/apps/resmonpro/var/history.sqlite3")
RANGES = {1: 60, 24: 300, 168: 900, 720: 3600}
RETENTION = 30 * 86400


def cpu_temperature():
    readings = []
    for hwmon in Path('/sys/class/hwmon').glob('hwmon*'):
        try:
            if (hwmon / 'name').read_text().strip() not in ('k10temp', 'coretemp', 'zenpower'):
                continue
            for sensor in hwmon.glob('temp*_input'):
                value = float(sensor.read_text()) / 1000
                if -20 <= value <= 150:
                    readings.append(value)
        except (OSError, ValueError):
            continue
    return max(readings) if readings else None


def live():
    with open("/proc/stat") as file:
        ticks = list(map(int, file.readline().split()[1:9]))
    total = sum(ticks)
    idle = ticks[3] + ticks[4]
    memory = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        if key in ("MemAvailable", "MemTotal"):
            memory[key] = int(value.split()[0])
    used = 100 * (1 - memory["MemAvailable"] / memory["MemTotal"])
    return {"total": total, "idle": idle, "user_ticks": ticks[0] + ticks[1],
            "system_ticks": ticks[2] + ticks[5] + ticks[6], "iowait_ticks": ticks[4], "memory": used,
            "memory_gib": memory["MemTotal"] / 1048576,
            "used_gib": (memory["MemTotal"] - memory["MemAvailable"]) / 1048576,
            "cores": os_cpu_count(), "physical_cores": next((int(line.split(":", 1)[1]) for line in Path("/proc/cpuinfo").read_text().splitlines() if line.startswith("cpu cores")), os_cpu_count()), "ts": int(time.time()),
            "cpu_temperature": cpu_temperature(), "loadavg": list(getloadavg()),
            "cpu_name": next((line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
                              if line.startswith('model name')), 'CPU')}


def gpu_live():
    def read(path, divisor=1):
        try:
            value = float(path.read_text()) / divisor
            return value if value >= 0 else None
        except (OSError, ValueError):
            return None
    try:
        engines = json.loads(Path('/run/resmonpro-gpu/engines.json').read_text())
        if not 0 <= time.time() - engines['ts'] <= 10:
            engines = {}
    except (OSError, ValueError, KeyError):
        engines = {}
    result = []
    for card in sorted(Path('/sys/class/drm').glob('card[0-9]*')):
        if not card.name[4:].isdigit():
            continue
        device = card / 'device'
        if not device.exists():
            continue
        temperatures = [read(hwmon / 'temp1_input',1000) for hwmon in (device / 'hwmon').glob('hwmon*')]
        temperature = max((v for v in temperatures if v is not None), default=None)
        total, used = read(device / 'mem_info_vram_total'), read(device / 'mem_info_vram_used')
        pci = device.resolve().name
        engine = engines.get('devices',{}).get(pci,{})
        result.append({'id': pci, 'card': card.name, 'busy':read(device / 'gpu_busy_percent'), 'temp':temperature,
            'ram':{'total':total,'used':used,'free':total-used if total is not None and used is not None else None},
            'engine':{'compute':engine.get('compute'),'encoder':engine.get('encoder')}})
    return result


def record_gpu(db, sample, cadence):
    db.execute("""CREATE TABLE IF NOT EXISTS gpu_samples (
        ts INTEGER,cadence INTEGER,device TEXT,card TEXT,busy REAL,temperature REAL,
        vram_total REAL,vram_used REAL,compute REAL,encoder REAL,PRIMARY KEY(cadence,ts,device))""")
    for gpu in gpu_live():
        values = (gpu['busy'],gpu['temp'],gpu['ram']['total'],gpu['ram']['used'],gpu['engine']['compute'],gpu['engine']['encoder'])
        if cadence == 60:
            count, *average = db.execute('SELECT COUNT(*),AVG(busy),AVG(temperature),AVG(vram_total),AVG(vram_used),AVG(compute),AVG(encoder) FROM gpu_samples WHERE cadence=3 AND device=? AND ts>? AND ts<=?',
                                        (gpu['id'],sample['ts']-60,sample['ts'])).fetchone()
            if count:
                values = average
        db.execute('INSERT OR IGNORE INTO gpu_samples VALUES (?,?,?,?,?,?,?,?,?,?)',
                   (sample['ts'],cadence,gpu['id'],gpu['card'],*values))
    db.execute('DELETE FROM gpu_samples WHERE cadence=? AND ts<?', (cadence,sample['ts']-(3600 if cadence==3 else RETENTION)))


def gpu_history(db,start,end,bucket,cadence):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='gpu_samples'").fetchone():
        return []
    rows = db.execute("""SELECT device,MAX(card),MAX(ts),ROUND(AVG(busy),2),ROUND(AVG(temperature),2),
        AVG(vram_total),AVG(vram_used),ROUND(AVG(compute),2),ROUND(AVG(encoder),2)
        FROM gpu_samples WHERE cadence=? AND ts BETWEEN ? AND ? GROUP BY device,ts / ? ORDER BY device,MAX(ts)""",(cadence,start,end,bucket)).fetchall()
    gpus = {}
    for device,card,*point in rows:
        gpus.setdefault(device,{'id':device,'card':card,'points':[]})['points'].append(point)
    return list(gpus.values())


def record_details(db, table, sample, previous, boot):
    columns = {row[1] for row in db.execute(f'PRAGMA table_info({table})')}
    for name in ('user_ticks', 'system_ticks', 'iowait_ticks', 'cpu_user', 'cpu_system', 'cpu_iowait'):
        if name not in columns:
            db.execute(f'ALTER TABLE {table} ADD COLUMN {name} REAL')
    rates = [None] * 3
    if previous and previous[1] == boot:
        old = db.execute(f'SELECT user_ticks,system_ticks,iowait_ticks FROM {table} WHERE ts=?', (previous[0],)).fetchone()
        elapsed = sample['total'] - previous[2]
        gap = sample['ts'] - previous[0]
        if old and all(v is not None for v in old) and elapsed > 0 and 0 < gap <= (10 if table == 'live_samples' else 120):
            rates = [100 * (sample[key] - value) / elapsed for key, value in zip(('user_ticks','system_ticks','iowait_ticks'), old)]
            rates = [v if 0 <= v <= 100 else None for v in rates]
    db.execute(f'UPDATE {table} SET user_ticks=?,system_ticks=?,iowait_ticks=?,cpu_user=?,cpu_system=?,cpu_iowait=? WHERE ts=?',
               (sample['user_ticks'],sample['system_ticks'],sample['iowait_ticks'],*rates,sample['ts']))
    cadence = 3 if table == 'live_samples' else 60
    record_gpu(db, sample, cadence)
    db.execute("""CREATE TABLE IF NOT EXISTS network_samples (
        ts INTEGER, cadence INTEGER, name TEXT, boot TEXT, rx INTEGER, tx INTEGER,
        receive REAL, transmit REAL, PRIMARY KEY(cadence,ts,name))""")
    # Physical NICs only: bridges, Docker and virtual ports otherwise count traffic twice.
    for interface in sorted(Path('/sys/class/net').iterdir()):
        if not (interface / 'device').exists() or (interface / 'wireless').exists() or (interface / 'phy80211').exists():
            continue
        try:
            rx = int((interface / 'statistics/rx_bytes').read_text())
            tx = int((interface / 'statistics/tx_bytes').read_text())
        except (OSError, ValueError):
            continue
        old = db.execute('SELECT ts,boot,rx,tx FROM network_samples WHERE cadence=? AND name=? ORDER BY ts DESC LIMIT 1', (cadence,interface.name)).fetchone()
        receive = transmit = None
        if old and old[1] == boot and 0 < sample['ts'] - old[0] <= cadence * 2 + 4:
            seconds = sample['ts'] - old[0]
            receive = (rx - old[2]) / seconds if rx >= old[2] else None
            transmit = (tx - old[3]) / seconds if tx >= old[3] else None
        db.execute('INSERT OR IGNORE INTO network_samples VALUES (?,?,?,?,?,?,?,?)',
                   (sample['ts'],cadence,interface.name,boot,rx,tx,receive,transmit))
    db.execute('DELETE FROM network_samples WHERE cadence=? AND ts<?', (cadence,sample['ts'] - (3600 if cadence == 3 else RETENTION)))


def network_history(db, start, end, bucket, cadence):
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='network_samples'").fetchone()
    if not exists:
        return []
    rows = db.execute("""SELECT name,MAX(ts),AVG(receive),AVG(transmit) FROM network_samples
        WHERE cadence=? AND ts BETWEEN ? AND ? GROUP BY name, ts / ? ORDER BY name, MAX(ts)""", (cadence,start,end,bucket)).fetchall()
    networks = {}
    for name, ts, receive, transmit in rows:
        interface = Path('/sys/class/net') / name
        if (interface / 'wireless').exists() or (interface / 'phy80211').exists():
            continue
        networks.setdefault(name, []).append([ts, receive, transmit])
    return [{'name': name, 'points': points} for name,points in networks.items()]


def collect():
    sample = live()
    total, idle, used, now = (sample[key] for key in ("total", "idle", "memory", "ts"))
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    with closing(sqlite3.connect(DB, timeout=10)) as db, db:
        db.execute("""CREATE TABLE IF NOT EXISTS samples (
            ts INTEGER PRIMARY KEY, cpu REAL, memory REAL NOT NULL,
            boot TEXT NOT NULL, total INTEGER NOT NULL, idle INTEGER NOT NULL)""")
        if 'temperature' not in {row[1] for row in db.execute('PRAGMA table_info(samples)')}:
            db.execute('ALTER TABLE samples ADD COLUMN temperature REAL')
        previous = db.execute(
            "SELECT ts, boot, total, idle FROM samples ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        if previous and previous[1] == boot and 0 < now - previous[0] < 10:
            return
        cpu = None
        if previous and previous[1] == boot and 10 <= now - previous[0] <= 120:
            elapsed = total - previous[2]
            idle_elapsed = idle - previous[3]
            if elapsed > 0 and 0 <= idle_elapsed <= elapsed:
                cpu = 100 * (1 - idle_elapsed / elapsed)
        db.execute("INSERT OR IGNORE INTO samples (ts,cpu,memory,boot,total,idle,temperature) VALUES (?,?,?,?,?,?,?)",
                   (now, cpu, used, boot, total, idle, sample["cpu_temperature"]))
        record_details(db, "samples", sample, previous, boot)
        db.execute("DELETE FROM samples WHERE ts < ?", (now - RETENTION,))


def query(hours):
    bucket = RANGES[hours]
    end = int(time.time())
    start = end - hours * 3600
    with closing(sqlite3.connect(DB.as_uri() + "?mode=ro", uri=True, timeout=3)) as db:
        points = db.execute("""
            SELECT MAX(ts), ROUND(AVG(cpu), 2), ROUND(AVG(memory), 2), ROUND(AVG(temperature), 2),
                ROUND(AVG(cpu_user),2),ROUND(AVG(cpu_system),2),ROUND(AVG(cpu_iowait),2)
            FROM samples WHERE ts BETWEEN ? AND ?
            GROUP BY ts / ? ORDER BY MAX(ts)
        """, (start, end, bucket)).fetchall()
        latest = db.execute(
            "SELECT ts, ROUND(cpu, 2), ROUND(memory, 2), temperature,ROUND(cpu_user,2),ROUND(cpu_system,2),ROUND(cpu_iowait,2) FROM samples ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        networks = network_history(db, start, end, bucket, 60)
        gpus = gpu_history(db,start,end,bucket,60)
    return {"start": start, "end": end, "bucket": bucket, "points": points, "latest": latest,"networks": networks,"gpus": gpus}


def collect_recent():
    sample = live()
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    with closing(sqlite3.connect(DB, timeout=10)) as db, db:
        db.execute("""CREATE TABLE IF NOT EXISTS live_samples (
            ts INTEGER PRIMARY KEY, cpu REAL, memory REAL, temperature REAL,
            boot TEXT, total INTEGER, idle INTEGER)""")
        old = db.execute('SELECT ts,boot,total,idle FROM live_samples ORDER BY ts DESC LIMIT 1').fetchone()
        cpu = None
        if old and old[1] == boot and 0 < sample['ts'] - old[0] <= 10:
            elapsed = sample['total'] - old[2]
            idle = sample['idle'] - old[3]
            if elapsed > 0 and 0 <= idle <= elapsed:
                cpu = 100 * (1 - idle / elapsed)
        db.execute('INSERT OR IGNORE INTO live_samples (ts,cpu,memory,temperature,boot,total,idle) VALUES (?,?,?,?,?,?,?)',
                   (sample['ts'], cpu, sample['memory'], sample['cpu_temperature'], boot, sample['total'], sample['idle']))
        record_details(db, 'live_samples', sample, old, boot)
        db.execute('DELETE FROM live_samples WHERE ts < ?', (sample['ts'] - 3600,))


def recent():
    end = int(time.time()) // 3 * 3
    start = end - 177
    with closing(sqlite3.connect(DB.as_uri() + '?mode=ro', uri=True, timeout=3)) as db:
        points = db.execute('SELECT ts,ROUND(cpu,2),ROUND(memory,2),temperature,ROUND(cpu_user,2),ROUND(cpu_system,2),ROUND(cpu_iowait,2) FROM live_samples WHERE ts BETWEEN ? AND ? ORDER BY ts DESC LIMIT 60', (start,end)).fetchall()[::-1]
        networks = network_history(db, start, end, 3, 3)
        gpus = gpu_history(db,start,end,3,3)
    return {'start': start, 'end': end, 'bucket': 3, 'points': points, 'latest': points[-1] if points else None,'networks': networks,'gpus':gpus}


def run():
    last_minute = None
    while True:
        try:
            collect_recent()
            minute = int(time.time()) // 60
            if minute != last_minute:
                collect()
                last_minute = minute
        except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
            print(f"Sampling failed: {exc}", file=sys.stderr, flush=True)
        time.sleep(max(.1, 3 - time.time() % 3))


if __name__ == "__main__":
    run()
