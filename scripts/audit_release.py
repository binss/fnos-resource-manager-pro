#!/usr/bin/env python3
"""Check public FPKs contain no runtime data or local-only configuration."""
import io
import json
from pathlib import Path
import tarfile

ROOT=Path(__file__).resolve().parents[1]
for path in sorted((ROOT/'dist/public').glob('*.fpk')):
    with tarfile.open(path) as outer:
        contents=outer.extractfile('app.tgz').read()
    with tarfile.open(fileobj=io.BytesIO(contents)) as archive:
        for member in archive.getmembers():
            name=member.name
            assert not any(part in ('seed','test-data','private','__pycache__') for part in Path(name).parts),name
            assert not name.endswith(('.jsonl','.sqlite3','.sqlite','.db','.log','.pid','.pyc')),name
            if member.isfile() and name.endswith(('.py','.cgi','.js','.html','.json')):
                data=archive.extractfile(member).read()
                assert b'/Users/' not in data and b'/vol2/1000/' not in data,name
            if name.endswith('device-aliases.json'):
                assert json.loads(archive.extractfile(member).read())=={},name
        if path.name.startswith('resmonpro-'):
            candidate=next(member for member in archive.getmembers() if member.name.endswith('ui/images/icon_256.png'))
            assert archive.extractfile(candidate).read()==(ROOT/'packages/resmonpro/app/ui/images/icon_256.png').read_bytes()
    print('PASS:',path.name,'contains public defaults; no runtime data or local configuration')
