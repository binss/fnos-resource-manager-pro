import concurrent.futures
import datetime as dt
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest

spec=importlib.util.spec_from_file_location('storage',Path(__file__).resolve().parents[1]/'packages/resmonpro/app/temperature/storage.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
Store=module.Store
TZ=dt.timezone(dt.timedelta(hours=8))

def sample(stamp=None,values=(40.0,60.0)):
    stamp=int(time.time()) if stamp is None else stamp
    return {'timestamp':dt.datetime.fromtimestamp(stamp,TZ).isoformat(timespec='seconds'),
            'host':'test-nas','errors':[], 'readings':[
                {'key':key,'kind':kind,'model':key,'device':key,'sensor':'temp1',
                 'primary':True,'temperature_c':value,'hardware_alarm':False,'at_critical':False,
                 'max_c':80,'critical_c':90}
                for key,kind,value in zip(('disk:SERIAL:Composite','cpu:device:Tctl'),('disk','cpu'),values)]}

class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name)

    def test_atomic_and_duplicate(self):
        s=sample();self.assertTrue(self.store.record(s));self.assertFalse(self.store.record(s))
        self.assertEqual(self.store.count(),1)
        self.assertEqual(next(iter(self.store.today().values()))['count'],1)
        bad=sample(int(time.time())+30, (50,float('nan')))
        with self.assertRaises(ValueError):self.store.record(bad)
        self.assertEqual(self.store.count(),1)
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM reading_points').fetchone()[0],2)

    def test_concurrent_duplicate_not_double_counted(self):
        s=sample()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:self.store.record(s),range(8)))
        self.assertEqual(sum(results),1)
        self.assertEqual(self.store.count(),1)

    def test_summary_retention_and_index(self):
        now=int(time.time())
        for age in (370,31,0):self.store.record(sample(now-age*86400))
        self.store.maintain(now=now,force=True)
        self.assertEqual(self.store.count(),1)
        self.assertEqual(len(self.store.daily(365)),4)  # 31-day detail expired; its daily stats remain.
        with self.store.connect() as db:
            plan=str(db.execute('EXPLAIN QUERY PLAN SELECT key,temperature FROM reading_points WHERE ts>=?',(now-3600,)).fetchall())
            self.assertIn('SEARCH',plan)
            self.assertNotIn('SCAN reading_points',plan)
        self.assertEqual(self.store.health()['integrity'][:2],'ok')

    def test_minute_cadence_is_not_a_gap(self):
        now=int(time.time())
        for seconds in (120,60,0):self.store.record(sample(now-seconds))
        self.assertEqual(self.store.count(),3)
        self.assertFalse(any(e['kind']=='gap' for e in self.store.events()))
        self.assertEqual(self.store.history(1)['bucket_seconds'],60)

    def test_gap_failure_and_restart(self):
        now=int(time.time());self.store.record(sample(now-200));self.store.record(sample(now))
        self.store.record_failure('sensor unavailable')
        events=self.store.events()
        self.assertEqual({r['kind'] for r in events},{'gap','error'})
        self.assertEqual(Store(self.tmp.name).count(),2)
        series=self.store.history(1)
        self.assertEqual(len(series['series']),2)
        self.assertTrue(all(len(point)==4 for ps in series['series'].values() for point in ps))

    def test_backup_rolling_and_readable(self):
        self.store.record(sample());now=int(time.time())
        for day in range(9):self.store.maintain(now=now+day*86400,force=True)
        files=sorted(self.store.backups.glob('daily-*.sqlite3'))
        self.assertEqual(len(files),7)
        with sqlite3.connect(files[-1]) as db:
            self.assertEqual(db.execute('PRAGMA quick_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM reading_points').fetchone()[0],2)

    def test_migrate_legacy_and_rescue_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            s=sample();path=Path(directory)/'history.sqlite3'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE samples(ts TEXT PRIMARY KEY,payload TEXT)')
                db.execute('CREATE TABLE readings(ts TEXT,key TEXT,temperature REAL,payload TEXT,PRIMARY KEY(ts,key))')
                db.execute('CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT)')
                db.execute('INSERT INTO samples VALUES (?,?)',(s['timestamp'],json.dumps(s)))
                for r in s['readings']:db.execute('INSERT INTO readings VALUES (?,?,?,?)',(s['timestamp'],r['key'],r['temperature_c'],json.dumps(r)))
            migrated=Store(directory)
            self.assertEqual(migrated.count(),1)
            self.assertEqual(len(migrated.today()),2)
            with sqlite3.connect(migrated.backups/'before-schema-v2.sqlite3') as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM readings').fetchone()[0],2)
            with migrated.connect() as db:
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],2)
                self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='samples'").fetchone())
            self.assertEqual(Store(directory).count(),1)

    def test_migration_rolls_back_on_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            s=sample();path=Path(directory)/'history.sqlite3'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE samples(ts TEXT PRIMARY KEY,payload TEXT)')
                db.execute('CREATE TABLE readings(ts TEXT,key TEXT,temperature REAL,payload TEXT)')
                db.execute('INSERT INTO samples VALUES (?,?)',(s['timestamp'],json.dumps(s)))
            with self.assertRaisesRegex(RuntimeError,'count mismatch'):Store(directory)
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM samples').fetchone()[0],1)
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],0)
                self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='sample_runs'").fetchone())

if __name__=='__main__':unittest.main(verbosity=2)
