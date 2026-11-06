#!/usr/bin/env python3
"""Copy stopped legacy temperature data into Pro, with a separate verified backup."""
import argparse
from contextlib import closing
import datetime as dt
import json
import os
from pathlib import Path
import pwd
import shutil
import sqlite3
import tempfile

TABLES=('sample_runs','reading_points','sensors','daily_statistics','collection_events')

def inventory(path):
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
        if db.execute('pragma quick_check').fetchone()[0]!='ok':raise RuntimeError('SQLite integrity check failed')
        return {table:db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in TABLES}

def copy_database(source,destination):
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(destination)) as dst:
        src.backup(dst)
    if inventory(source)!=inventory(destination):raise RuntimeError('Migrated row counts differ')

def migrate(source,destination,backup,owner=None):
    source,destination,backup=map(lambda p:Path(p).resolve(),(source,destination,backup))
    if not (source/'history.sqlite3').is_file():raise RuntimeError('Legacy temperature database not found')
    if destination.exists() and any(destination.iterdir()):raise RuntimeError('Destination is not empty; refusing to overwrite')
    if backup.exists():raise RuntimeError('Backup destination already exists')
    pidfile=source/'app.pid'
    if pidfile.exists():
        pid=pidfile.read_text().strip()
        if pid.isdigit() and Path('/proc',pid,'cmdline').exists():raise RuntimeError('Stop the legacy temperature service first')
    before=inventory(source/'history.sqlite3')
    backup.parent.mkdir(parents=True,exist_ok=True)
    shutil.copytree(source,backup)
    # SQLite backup makes an independent, consistent snapshot even if a WAL is present.
    for suffix in ('-wal','-shm'):(backup/('history.sqlite3'+suffix)).unlink(missing_ok=True)
    (backup/'history.sqlite3').unlink()
    copy_database(source/'history.sqlite3',backup/'history.sqlite3')
    destination.parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix='.temperature-migration-',dir=destination.parent))
    try:
        shutil.copytree(backup,staging,dirs_exist_ok=True)
        for name in ('app.pid','.instance.lock'):(staging/name).unlink(missing_ok=True)
        after=inventory(staging/'history.sqlite3')
        if before!=after:raise RuntimeError('Data validation failed')
        report={'migrated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'rows':after,'backup_files':len(list((staging/'backups').glob('*.sqlite3')))}
        (staging/'migration-info.json').write_text(json.dumps(report,indent=2)+'\n')
        if owner:
            user=pwd.getpwnam(owner)
            for path in [staging,*staging.rglob('*')]:os.chown(path,user.pw_uid,user.pw_gid)
        if destination.exists():destination.rmdir()
        staging.replace(destination)
        return report
    finally:
        if staging.exists():shutil.rmtree(staging)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path('/var/apps/thermoboard/var'))
    parser.add_argument('--destination',type=Path,default=Path('/var/apps/resmonpro/var/temperature'))
    parser.add_argument('--backup',type=Path,required=True)
    parser.add_argument('--owner',default='resmonpro')
    args=parser.parse_args()
    print(json.dumps(migrate(args.source,args.destination,args.backup,args.owner),indent=2))
