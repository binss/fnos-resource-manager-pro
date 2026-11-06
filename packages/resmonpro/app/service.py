"""Supervise the resource and temperature workers under the package user."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading

ROOT=Path(__file__).resolve().parent

def run(commands=None):
    variable=Path(os.environ.get('TRIM_PKGVAR','/var/apps/resmonpro/var'))
    temperature=variable/'temperature'
    temperature.mkdir(parents=True,exist_ok=True,mode=0o700)
    commands=commands or [
        ([sys.executable,str(ROOT/'monitor.py')],dict(os.environ)),
        ([sys.executable,str(ROOT/'temperature/server.py')],{**os.environ,'TRIM_PKGVAR':str(temperature),'RESMONPRO_TEMPERATURE_PORT':'39188'})
    ]
    stop=threading.Event()
    def shutdown(*_):stop.set()
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,shutdown)
    workers=[]
    try:
        for command,environment in commands:
            workers.append(subprocess.Popen(command,env=environment))
        while not stop.wait(.5):
            for worker in workers:
                if worker.poll() is not None:
                    raise RuntimeError('Collector worker exited with status '+str(worker.returncode))
    finally:
        for worker in workers:
            if worker.poll() is None:worker.terminate()
        for worker in workers:
            try:worker.wait(timeout=10)
            except subprocess.TimeoutExpired:worker.kill();worker.wait()
    return 0

if __name__=='__main__':
    try:raise SystemExit(run())
    except Exception as error:
        print('Resource Manager Pro stopped: '+str(error),file=sys.stderr,flush=True)
        raise SystemExit(1)
