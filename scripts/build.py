#!/usr/bin/env python3
"""Stage clean FPKs. Default builds never include private icons or device aliases."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
PACKAGES=('resmonpro',)


def manifest_value(folder,key):
    for line in (folder/'manifest').read_text().splitlines():
        name,sep,value=line.partition('=')
        if sep and name.strip()==key:return value.strip()
    raise ValueError('Missing manifest key: '+key)


def build(package,fnpack,local=False):
    mode='local' if local else 'public'
    source=ROOT/'packages'/package
    stage=ROOT/'build'/mode/package
    if stage.exists():shutil.rmtree(stage)
    stage.parent.mkdir(parents=True,exist_ok=True)
    shutil.copytree(source,stage,ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.jsonl','*.sqlite*','*.log','*.fpk','seed','test-data'))
    if package=='resmonpro' and local:
        icon=ROOT/'assets/private/fnos-resource-manager.png'
        if icon.is_file():
            for name in ('ICON.PNG','ICON_256.PNG','app/ui/images/icon_64.png','app/ui/images/icon_256.png'):
                shutil.copyfile(icon,stage/name)
        aliases=ROOT/'assets/private/device-aliases.json'
        if aliases.is_file():
            data=json.loads(aliases.read_text())
            if not isinstance(data,dict):raise ValueError('Device aliases must be an object')
            shutil.copyfile(aliases,stage/'app/ui/device-aliases.json')
    env={**os.environ,'COPYFILE_DISABLE':'1'}
    subprocess.run([str(fnpack),'build'],cwd=stage,env=env,check=True)
    result=stage/(manifest_value(stage,'appname')+'.fpk')
    destination=ROOT/'dist'/mode/(package+'-'+manifest_value(stage,'version')+'.fpk')
    destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(result,destination)
    return destination


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package',nargs='?',choices=PACKAGES)
    parser.add_argument('--all',action='store_true')
    parser.add_argument('--local',action='store_true',help='Opt into ignored local fnOS icon and device aliases')
    parser.add_argument('--fnpack',type=Path)
    args=parser.parse_args()
    if not args.all and not args.package:parser.error('Choose a package or --all')
    fnpack=args.fnpack or (Path(os.environ['FNPACK']) if os.environ.get('FNPACK') else None)
    fnpack=fnpack or (ROOT/'tools/private/fnpack' if (ROOT/'tools/private/fnpack').is_file() else None)
    fnpack=fnpack or (Path(shutil.which('fnpack')) if shutil.which('fnpack') else None)
    if fnpack is None:parser.error('Install official fnpack and pass --fnpack /path/to/fnpack (see README)')
    outputs=[build(package,fnpack.resolve(),args.local) for package in (PACKAGES if args.all else (args.package,))]
    hashes=''.join(hashlib.sha256(file.read_bytes()).hexdigest()+'  '+file.name+'\n' for file in outputs)
    (outputs[0].parent/'SHA256SUMS').write_text(hashes)
    print(hashes,end='')
    for output in outputs:print(output.relative_to(ROOT))

if __name__=='__main__':main()
