"""Transactional temperature history, indexed queries and bounded local backups."""
from contextlib import contextmanager
import datetime as dt
import json
import os
from pathlib import Path
import sqlite3
import time

TZ = dt.timezone(dt.timedelta(hours=8))
RAW_DAYS, SUMMARY_DAYS, BACKUP_DAYS = 30, 365, 7
SAMPLE_INTERVAL_SECONDS = 60


def epoch(value):
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError('Sample timestamp must include timezone')
    return int(parsed.timestamp())


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'history.sqlite3'
        self.backups = self.directory / 'backups'
        self.backups.mkdir(exist_ok=True, mode=0o700)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version > 2:
                raise RuntimeError('Database version is newer than this application')
            result = db.execute('PRAGMA quick_check').fetchone()[0]
            if result != 'ok':
                raise RuntimeError('Database quick_check failed: ' + result)
            legacy = bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='samples'").fetchone())
        if version < 2:
            if legacy:
                self.backup(self.backups / 'before-schema-v2.sqlite3')
            self.migrate(legacy)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('PRAGMA busy_timeout=20000')
            with db:
                yield db
        finally:
            db.close()

    def migrate(self, legacy):
        with self.connect() as db:
            # Keep all DDL and imported rows in a single explicit transaction.
            db.execute('BEGIN IMMEDIATE')
            for sql in (
                'CREATE TABLE IF NOT EXISTS sensors (key TEXT PRIMARY KEY, metadata TEXT NOT NULL, last_seen INTEGER NOT NULL)',
                'CREATE TABLE IF NOT EXISTS sample_runs (ts INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, host TEXT NOT NULL, errors TEXT NOT NULL)',
                '''CREATE TABLE IF NOT EXISTS reading_points (
                    ts INTEGER NOT NULL, key TEXT NOT NULL, temperature REAL NOT NULL,
                    hardware_alarm INTEGER NOT NULL, at_critical INTEGER NOT NULL,
                    critical REAL, max_temperature REAL, PRIMARY KEY(ts,key)) WITHOUT ROWID''',
                'CREATE INDEX IF NOT EXISTS points_key_ts ON reading_points(key,ts)',
                '''CREATE TABLE IF NOT EXISTS daily_statistics (
                    day TEXT NOT NULL, key TEXT NOT NULL, count INTEGER NOT NULL,
                    total REAL NOT NULL, minimum REAL NOT NULL, maximum REAL NOT NULL,
                    PRIMARY KEY(day,key)) WITHOUT ROWID''',
                '''CREATE TABLE IF NOT EXISTS collection_events (
                    id INTEGER PRIMARY KEY, ts INTEGER NOT NULL, kind TEXT NOT NULL,
                    message TEXT NOT NULL, start_ts INTEGER, end_ts INTEGER)''',
                'CREATE INDEX IF NOT EXISTS events_ts ON collection_events(ts)',
                'CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)',
            ):
                db.execute(sql)
            if legacy:
                count = db.execute('SELECT COUNT(*) FROM readings').fetchone()[0]
                for (payload,) in db.execute('SELECT payload FROM samples ORDER BY ts').fetchall():
                    self._insert(db, json.loads(payload), detect_gap=False)
                actual = db.execute('SELECT COUNT(*) FROM reading_points').fetchone()[0]
                if actual != count:
                    raise RuntimeError(f'Migration row count mismatch: {count} != {actual}')
                for table in ('readings', 'samples', 'metadata'):
                    db.execute('DROP TABLE IF EXISTS ' + table)
                db.execute("INSERT OR REPLACE INTO settings VALUES ('seed-imported','1')")
                self._event(db, int(time.time()), 'migration', f'迁移完成，保留 {actual} 条温度记录')
            db.execute('PRAGMA user_version=2')

    @staticmethod
    def _event(db, now, kind, message, start=None, end=None):
        db.execute('INSERT INTO collection_events(ts,kind,message,start_ts,end_ts) VALUES (?,?,?,?,?)',
                   (now, kind, message[:2000], start, end))

    def _insert(self, db, sample, detect_gap=True):
        ts = epoch(sample['timestamp'])
        rows = sample['readings']
        keys = [row['key'] for row in rows]
        if len(set(keys)) != len(keys):
            raise ValueError('Duplicate sensor key in one sample')
        # Reject invalid measurements before the transaction can become visible.
        for row in rows:
            value = row['temperature_c']
            if not isinstance(value, (int, float)) or not -30 <= value <= 150:
                raise ValueError('Invalid sensor temperature')
        previous = db.execute('SELECT MAX(ts) FROM sample_runs').fetchone()[0] if detect_gap else None
        inserted = db.execute('INSERT OR IGNORE INTO sample_runs VALUES (?,?,?,?)',
                              (ts, sample['timestamp'], sample.get('host', ''), json.dumps(sample.get('errors', []), ensure_ascii=False)))
        if not inserted.rowcount:
            return False
        if previous is not None and ts - previous > SAMPLE_INTERVAL_SECONDS * 3:
            self._event(db, ts, 'gap', f'采样间隔 {ts-previous} 秒（含关机、应用停止或采集失败）', previous, ts)
        if detect_gap:
            errors = json.dumps(sample.get('errors', []), ensure_ascii=False, sort_keys=True)
            old_errors = db.execute("SELECT value FROM settings WHERE key='sensor-errors'").fetchone()
            if errors != (old_errors[0] if old_errors else '[]'):
                self._event(db, ts, 'partial' if sample.get('errors') else 'recovery',
                            ('部分传感器无法读取：'+errors) if sample.get('errors') else '传感器读取已恢复')
                db.execute("INSERT OR REPLACE INTO settings VALUES ('sensor-errors',?)", (errors,))
        day = dt.datetime.fromtimestamp(ts, TZ).date().isoformat()
        for row in rows:
            meta = {k: v for k, v in row.items() if k not in ('temperature_c', 'hardware_alarm', 'at_critical', 'critical_c', 'max_c')}
            db.execute('''INSERT INTO sensors VALUES (?,?,?) ON CONFLICT(key) DO UPDATE
                          SET metadata=excluded.metadata,last_seen=excluded.last_seen
                          WHERE excluded.last_seen>=sensors.last_seen''',
                       (row['key'], json.dumps(meta, ensure_ascii=False), ts))
            value = row['temperature_c']
            db.execute('INSERT INTO reading_points VALUES (?,?,?,?,?,?,?)',
                       (ts, row['key'], value, int(bool(row.get('hardware_alarm'))),
                        int(bool(row.get('at_critical'))), row.get('critical_c'), row.get('max_c')))
            db.execute('''INSERT INTO daily_statistics VALUES (?,?,1,?,?,?)
                          ON CONFLICT(day,key) DO UPDATE SET count=count+1,
                          total=total+excluded.total,minimum=MIN(minimum,excluded.minimum),
                          maximum=MAX(maximum,excluded.maximum)''',
                       (day, row['key'], value, value, value))
        return True

    def record(self, sample):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            return self._insert(db, sample)

    def import_seed(self, paths):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM settings WHERE key='seed-imported'").fetchone():
                return
            for path in sorted(paths):
                for line in path.read_text().splitlines():
                    if line.strip():
                        self._insert(db, json.loads(line), detect_gap=False)
            db.execute("INSERT INTO settings VALUES ('seed-imported','1')")

    def record_failure(self, error):
        with self.connect() as db:
            self._event(db, int(time.time()), 'error', str(error))

    def today(self):
        day = dt.datetime.now(TZ).date().isoformat()
        with self.connect() as db:
            return {key: dict(minimum_c=lo, average_c=round(total/count, 2), maximum_c=hi, count=count)
                    for key, count, total, lo, hi in db.execute(
                        'SELECT key,count,total,minimum,maximum FROM daily_statistics WHERE day=?', (day,))}

    def count(self):
        with self.connect() as db:
            return db.execute('SELECT COUNT(*) FROM sample_runs').fetchone()[0]

    def history(self, hours):
        bucket = 60 if hours <= 1 else 120 if hours <= 6 else 300 if hours <= 24 else 1800 if hours <= 168 else 7200
        cutoff = int(time.time()) - hours * 3600
        with self.connect() as db:
            rows = db.execute('''SELECT key,ts/? AS bucket,AVG(temperature),MIN(temperature),MAX(temperature),COUNT(*)
                                  FROM reading_points WHERE ts>=? GROUP BY key,bucket ORDER BY bucket''', (bucket, cutoff)).fetchall()
        series, counts = {}, {}
        for key, stamp, avg, lo, hi, count in rows:
            series.setdefault(key, []).append([stamp * bucket * 1000, round(avg, 2), lo, hi])
            counts.setdefault(key, []).append(count)
        return {'series': series, 'counts': counts, 'bucket_seconds': bucket}

    def daily(self, days):
        first = (dt.datetime.now(TZ).date() - dt.timedelta(days=days-1)).isoformat()
        with self.connect() as db:
            rows = db.execute('''SELECT d.day,d.key,s.metadata,d.count,d.total,d.minimum,d.maximum
                                  FROM daily_statistics d JOIN sensors s USING(key)
                                  WHERE d.day>=? ORDER BY d.day,d.key''', (first,)).fetchall()
        return [dict(date=day, key=key, model=json.loads(meta).get('model', ''),
                     sensor=json.loads(meta).get('sensor', ''), count=count,
                     average_c=round(total/count, 3), minimum_c=lo, maximum_c=hi)
                for day, key, meta, count, total, lo, hi in rows]

    def events(self, limit=30):
        with self.connect() as db:
            return [dict(timestamp=dt.datetime.fromtimestamp(ts, TZ).isoformat(timespec='seconds'),
                         kind=kind, message=message, start_ts=start, end_ts=end)
                    for ts, kind, message, start, end in db.execute(
                        'SELECT ts,kind,message,start_ts,end_ts FROM collection_events ORDER BY id DESC LIMIT ?', (limit,))]

    def health(self):
        with self.connect() as db:
            first, last, count = db.execute('SELECT MIN(ts),MAX(ts),COUNT(*) FROM sample_runs').fetchone()
            points = db.execute('SELECT COUNT(*) FROM reading_points').fetchone()[0]
            version = db.execute('PRAGMA user_version').fetchone()[0]
            integrity = db.execute("SELECT value FROM settings WHERE key='integrity'").fetchone()
        def filesize(path):
            try:
                return path.stat().st_size
            except FileNotFoundError:
                return 0
        backups = sorted(self.backups.glob('daily-*.sqlite3'))
        return dict(schema_version=version, raw_retention_days=RAW_DAYS, daily_retention_days=SUMMARY_DAYS,
                    backup_retention_days=BACKUP_DAYS, stored_samples=count, stored_readings=points,
                    first_ts=first, latest_ts=last, database_bytes=filesize(self.path),
                    wal_bytes=filesize(Path(str(self.path)+'-wal')),
                    integrity=integrity[0] if integrity else '启动检查通过',
                    latest_backup=backups[-1].name if backups else None, events=self.events())

    def backup(self, destination):
        destination = Path(destination)
        temporary = destination.with_suffix('.new')
        try:
            with self.connect() as source:
                target = sqlite3.connect(temporary)
                try:
                    source.backup(target)
                    if target.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                        raise RuntimeError('Backup integrity check failed')
                finally:
                    target.close()
            temporary.chmod(0o600)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    def maintain(self, now=None, force=False):
        now = int(time.time()) if now is None else int(now)
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key='maintenance'").fetchone()
            if not force and row and now-int(row[0]) < 3600:
                return
            db.execute('DELETE FROM reading_points WHERE ts<?', (now-RAW_DAYS*86400,))
            db.execute('DELETE FROM sample_runs WHERE ts<?', (now-RAW_DAYS*86400,))
            db.execute('DELETE FROM collection_events WHERE ts<?', (now-RAW_DAYS*86400,))
            day = dt.datetime.fromtimestamp(now, TZ).date()
            db.execute('DELETE FROM daily_statistics WHERE day<?', ((day-dt.timedelta(days=SUMMARY_DAYS-1)).isoformat(),))
            db.execute('DELETE FROM sensors WHERE key NOT IN (SELECT key FROM daily_statistics) AND key NOT IN (SELECT key FROM reading_points)')
        destination = self.backups / f'daily-{day.isoformat()}.sqlite3'
        if not destination.exists():
            with self.connect() as db:
                result = db.execute('PRAGMA quick_check').fetchone()[0]
                if result != 'ok':
                    raise RuntimeError('Database integrity check failed: '+result)
                db.execute("INSERT OR REPLACE INTO settings VALUES ('integrity',?)", ('ok · '+day.isoformat(),))
            self.backup(destination)
        # Bounded rolling backups; retain the migration rescue copy separately.
        for old in sorted(self.backups.glob('daily-*.sqlite3'))[:-BACKUP_DAYS]:
            old.unlink()
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES ('maintenance',?)", (str(now),))
        with self.connect() as db:
            db.execute('PRAGMA wal_checkpoint(PASSIVE)')
