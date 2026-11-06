#!/usr/bin/python3
"""Local-only hardware monitor. The fnOS CGI gateway supplies authentication."""
import datetime as dt
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
import logging
from logging.handlers import RotatingFileHandler
import signal
import csv
import io
from storage import Store, RAW_DAYS, SUMMARY_DAYS, SAMPLE_INTERVAL_SECONDS
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
from collector import measure

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('TRIM_PKGVAR', str(ROOT / 'test-data')))
DATA.mkdir(parents=True, exist_ok=True)
DB = DATA / 'history.sqlite3'
lock = threading.Lock()
latest = None
collection_error = None

store = None
stop_event = threading.Event()
maintenance_error = None


def initialize():
    global store
    store = Store(DATA)
    # Existing history is migrated before first start; release packages carry no seed data.


def sample_once():
    global latest, collection_error
    try:
        sample = measure()
        store.record(sample)
        with lock:
            latest, collection_error = sample, None
    except Exception as exc:
        logging.exception('Temperature collection failed')
        with lock:
            collection_error = str(exc)
        try:
            store.record_failure(exc)
        except Exception:
            logging.exception('Could not persist collection failure')


def collect_loop():
    global maintenance_error
    deadline = time.monotonic() + SAMPLE_INTERVAL_SECONDS
    while not stop_event.wait(max(0, deadline-time.monotonic())):
        sample_once()
        try:
            store.maintain()
            maintenance_error = None
        except Exception as exc:
            maintenance_error = str(exc)
            logging.exception('Database maintenance failed')
        deadline += SAMPLE_INTERVAL_SECONDS
        if deadline < time.monotonic():
            deadline = time.monotonic() + SAMPLE_INTERVAL_SECONDS


def current():
    with lock:
        sample, error = latest, collection_error
    if sample is None:
        raise RuntimeError(error or '正在采集首个样本')
    return {'sample': sample, 'statistics': store.today(), 'stored_samples': store.count(),
            'collection_error': error, 'maintenance_error': maintenance_error,
            'sample_interval_seconds': SAMPLE_INTERVAL_SECONDS, 'retention_days': RAW_DAYS,
            'daily_retention_days': SUMMARY_DAYS}


def history(hours):
    return store.history(hours)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlsplit(self.path)
        try:
            if url.path == '/api/current':
                payload = json.dumps(current(), ensure_ascii=False).encode()
                mime = 'application/json; charset=utf-8'
            elif url.path == '/api/history':
                hours = int(parse_qs(url.query).get('hours', ['24'])[0])
                if hours not in (1, 6, 24, 168, 720):
                    raise ValueError('不支持的时间范围')
                payload = json.dumps(history(hours), ensure_ascii=False).encode()
                mime = 'application/json; charset=utf-8'
            elif url.path == '/api/storage':
                result = store.health()
                result['maintenance_error'] = maintenance_error
                payload = json.dumps(result, ensure_ascii=False).encode()
                mime = 'application/json; charset=utf-8'
            elif url.path in ('/api/daily', '/api/export.csv'):
                days = int(parse_qs(url.query).get('days', ['30'])[0])
                if days not in (7, 30, 90, 365):
                    raise ValueError('Unsupported days')
                rows = store.daily(days)
                if url.path == '/api/daily':
                    payload = json.dumps({'statistics': rows}, ensure_ascii=False).encode()
                    mime = 'application/json; charset=utf-8'
                else:
                    out = io.StringIO(newline='')
                    fields = ['date','key','model','sensor','count','minimum_c','average_c','maximum_c']
                    writer = csv.DictWriter(out, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(rows)
                    payload = ('\ufeff'+out.getvalue()).encode('utf-8')
                    mime = 'text/csv; charset=utf-8'
            elif url.path in ('/', '/index.html'):
                self.send_error(404)
                return
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Cache-Control', 'no-store')
            if url.path == '/api/export.csv':
                self.send_header('Content-Disposition', 'attachment; filename=temperature-daily.csv')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except ValueError as exc:
            self.send_error(400, 'Unsupported time range')
        except Exception:
            logging.exception('Request failed')
            self.send_error(503, 'Temperature collector unavailable')
    def log_message(self, *_):
        pass

if __name__ == '__main__':
    import fcntl
    os.umask(0o077)
    instance_lock = (DATA / '.instance.lock').open('a')
    fcntl.flock(instance_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    handler = RotatingFileHandler(DATA / 'collector.log', maxBytes=1048576, backupCount=3)
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    initialize()
    sample_once()
    # Maintenance (including daily backup) runs independently of HTTP requests.
    try:
        store.maintain(force=True)
    except Exception as exc:
        maintenance_error = str(exc)
        logging.exception('Initial database maintenance failed')
    server = ThreadingHTTPServer(('127.0.0.1', int(os.environ.get('RESMONPRO_TEMPERATURE_PORT', '39188'))), Handler)
    worker = threading.Thread(target=collect_loop, daemon=True)
    worker.start()
    def shutdown(signum, frame):
        stop_event.set()
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    try:
        server.serve_forever()
    finally:
        stop_event.set()
        worker.join(timeout=5)
        server.server_close()
