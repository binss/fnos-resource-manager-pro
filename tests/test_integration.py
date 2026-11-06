import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
TEMPERATURE=ROOT/'packages/resmonpro/app/temperature'
sys.path.insert(0,str(TEMPERATURE))
from storage import Store

def fixture():
    return {'timestamp':dt.datetime.now(dt.timezone.utc).isoformat(),'host':'test-nas','errors':[], 'readings':[
        {'key':'cpu:test:Tctl','kind':'cpu','model':'test-cpu','device':'test','sensor':'Tctl','primary':True,'temperature_c':42.0,'hardware_alarm':False,'at_critical':False,'max_c':None,'critical_c':None}]}

class IntegrationTests(unittest.TestCase):
    def test_temperature_http_api(self):
        with tempfile.TemporaryDirectory() as temp:
            os.environ['TRIM_PKGVAR']=temp
            try:
                spec=importlib.util.spec_from_file_location('temperature_server',TEMPERATURE/'server.py')
                server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)
            finally:os.environ.pop('TRIM_PKGVAR',None)
            server.measure=fixture;server.initialize();server.sample_once()
            http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
            thread=threading.Thread(target=http.serve_forever);thread.start()
            try:
                for route in ('/api/current','/api/history?hours=24','/api/storage','/api/daily?days=7'):
                    with urllib.request.urlopen('http://127.0.0.1:'+str(http.server_port)+route) as response:
                        self.assertEqual(response.status,200);self.assertIsInstance(json.load(response),dict)
            finally:http.shutdown();thread.join();http.server_close()

    def test_supervisor_stops_both_workers(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            worker='import os,time;from pathlib import Path;Path(os.environ["WORKER_PID"]).write_text(str(os.getpid()));time.sleep(60)'
            script='import sys,os;sys.path.insert(0,'+repr(str(ROOT/'packages/resmonpro/app'))+');import service;service.run([([sys.executable,"-c",'+repr(worker)+'],dict(os.environ,WORKER_PID='+repr(str(root/'one'))+')),([sys.executable,"-c",'+repr(worker)+'],dict(os.environ,WORKER_PID='+repr(str(root/'two'))+'))])'
            process=subprocess.Popen([sys.executable,'-c',script],env={**os.environ,'TRIM_PKGVAR':temp})
            try:
                deadline=time.time()+5
                while not all((root/name).exists() for name in ('one','two')) and time.time()<deadline:time.sleep(.05)
                self.assertTrue((root/'one').exists() and (root/'two').exists())
                pids=[int((root/name).read_text()) for name in ('one','two')]
                process.send_signal(signal.SIGTERM);self.assertEqual(process.wait(timeout=15),0)
                for pid in pids:
                    with self.assertRaises(ProcessLookupError):os.kill(pid,0)
            finally:
                if process.poll() is None:process.kill();process.wait()

if __name__=='__main__':unittest.main(verbosity=2)
