#!/usr/bin/env python3
"""Read-only check of native frontend assets and adapter structure on an installed fnOS."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--web',type=Path,default=Path('/usr/trim/www'))
args=parser.parse_args()
spec=importlib.util.spec_from_file_location('native',ROOT/'packages/resmonpro/app/native.py')
native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native);native.WEB=args.web
snapshot=json.loads((ROOT/'docs/fnos-assets.json').read_text())
for asset in snapshot['assets']:
    path=args.web/'assets'/asset['file']
    if not path.is_file():raise SystemExit('Missing native asset: '+asset['file'])
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    native.module(asset['route'])
    print(('MATCH' if digest==asset['sha256'] else 'CHANGED (adapter structure matched)'),asset['file'])
print('No system assets were changed.')
