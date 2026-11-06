#!/usr/bin/env python3
"""Inspect Git-visible source for common credential and private deployment-data leaks."""
import os
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
GIT=os.environ.get('GIT_BIN','git')
files={name for name in subprocess.check_output([GIT,'ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT,text=True).split('\0') if name}
patterns={
    'private key':r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----',
    'GitHub token':r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b',
    'cloud access key':r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
    'credential assignment':r'(?i)(?:password|api[_-]?key|secret|access[_-]?token)\s*[:=]\s*["\'][^"\'\n]{8,}["\']',
    'personal macOS path':r'/Users/[A-Za-z0-9_.-]+/',
    'private LAN address':r'\b(?:192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3})\b',
}
issues=[]
for name in sorted(files):
    path=ROOT/name
    if not path.is_file():continue
    if any(part in ('private','seed','test-data','__pycache__') for part in Path(name).parts) or name.endswith(('.fpk','.jsonl','.sqlite3','.sqlite','.db','.log','.pid','.pyc')):
        issues.append((name,'runtime or private file'))
    try:text=path.read_text()
    except UnicodeDecodeError:
        if path.suffix.lower()!='.png':issues.append((name,'unexpected binary'))
        continue
    for label,pattern in patterns.items():
        if re.search(pattern,text):issues.append((name,label))
for name,label in issues:print('REVIEW:',name,'('+label+')')
if issues:raise SystemExit('Source audit requires review; no matched secret values were printed.')
print('PASS:',len(files),'Git-visible files; no common credential or private deployment-data matches')
