"""Run once as root to enable the isolated DRM counter reader on this NAS."""
from pathlib import Path
import os
import shutil
import subprocess

if os.geteuid() != 0:
    raise SystemExit('Run as root')
folder = Path('/usr/local/lib/resmonpro')
folder.mkdir(mode=0o755,exist_ok=True)
source = Path(__file__).with_name('gpu-engines.py')
shutil.copyfile(source,folder / 'gpu-engines.py')
(folder / 'gpu-engines.py').chmod(0o644)
Path('/etc/systemd/system/resmonpro-gpu.service').write_text('''[Unit]
Description=Resource Manager Pro DRM engine counter reader
ConditionPathExists=/var/apps/resmonpro/target
After=local-fs.target
[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/lib/resmonpro/gpu-engines.py
Restart=on-failure
RestartSec=5
RuntimeDirectory=resmonpro-gpu
RuntimeDirectoryMode=0755
UMask=0022
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=read-only
PrivateTmp=yes
PrivateNetwork=yes
ProtectKernelTunables=yes
ProtectControlGroups=yes
CapabilityBoundingSet=CAP_DAC_READ_SEARCH CAP_SYS_PTRACE
RestrictAddressFamilies=AF_UNIX
ReadWritePaths=/run/resmonpro-gpu
[Install]
WantedBy=multi-user.target
''')
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemctl','enable','--now','resmonpro-gpu.service'],check=True)
subprocess.run(['systemctl','restart','resmonpro-gpu.service'],check=True)
