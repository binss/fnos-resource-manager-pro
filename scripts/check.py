#!/usr/bin/env python3
"""Offline source checks. Does not connect to the NAS or collect hardware data."""
import ast
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
for path in sorted((ROOT/'packages').rglob('*')):
    if path.suffix=='.py' or path.name=='index.cgi':ast.parse(path.read_text(),filename=str(path))
    if path.is_file() and path.parent.name=='cmd':subprocess.run(['bash','-n',str(path)],check=True)
if not shutil.which('node'):raise SystemExit('Node.js is needed for JavaScript checks')
with tempfile.TemporaryDirectory(prefix='resmon-source-check-') as directory:
    temporary=Path(directory)
    for path in sorted((ROOT/'packages').rglob('*')):
        if path.suffix=='.js':
            target=temporary/'check.mjs';target.write_text(path.read_text());subprocess.run(['node','--check',str(target)],check=True)
        if path.suffix=='.html':
            for index,part in enumerate(path.read_text().split('<script>')[1:]):
                target=temporary/('inline-'+str(index)+'.js');target.write_text(part.split('</script>',1)[0]);subprocess.run(['node','--check',str(target)],check=True)
subprocess.run([sys.executable,str(ROOT/'tests/test_storage.py')],check=True)
subprocess.run([sys.executable,str(ROOT/'tests/test_integration.py')],check=True)
subprocess.run([sys.executable,str(ROOT/'tests/test_mobile_data.py')],check=True)
subprocess.run(['node',str(ROOT/'tests/phone_gateway.cjs')],check=True)
subprocess.run(['node',str(ROOT/'tests/temperature_spline.cjs')],check=True)
subprocess.run(['node',str(ROOT/'tests/device_aliases.cjs')],check=True)
print('PASS: Python/CGI syntax, lifecycle shell syntax, JavaScript syntax, storage and chart regression checks')
