"""Verify process identity, counter deltas and redacted standalone responses."""
import importlib.util
import json
import os
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'packages/resmonpro/app'))
import mobile_data as mobile

class MobileDataTests(unittest.TestCase):
    def test_phone_entry_does_not_bootstrap_system_login(self):
        entry=ROOT/'packages/resmonpro/app/ui/index.cgi'
        for path in ('/', '/mobile', '/native'):
            env={**os.environ,'REQUEST_URI':'/cgi/ThirdParty/resmonpro/index.cgi'+path,
                 'REQUEST_METHOD':'GET','HTTP_USER_AGENT':'iPhone','QUERY_STRING':'theme=dark'}
            result=subprocess.run([sys.executable,str(entry)],env=env,capture_output=True,text=True,check=True)
            self.assertIn('phone.js',result.stdout)
            self.assertNotIn('/native/index.js',result.stdout)
            self.assertNotIn('Location:',result.stdout)
            self.assertNotIn('type="password"',result.stdout)

    def test_process_stat_with_spaces_and_parentheses(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);p=root/'42';p.mkdir()
            fields=['S']+['0']*21
            fields[11]='100';fields[12]='50';fields[19]='1000';fields[21]='3'
            (p/'stat').write_text('42 (worker (test) name) '+' '.join(fields))
            (p/'cgroup').write_text('0::/system.slice/demo.service\n')
            (p/'cmdline').write_text('must not be disclosed')
            rows=mobile.process_snapshot(root)
            self.assertEqual(rows[0]['name'],'worker (test) name')
            self.assertEqual(rows[0]['ticks'],150)
            self.assertEqual(rows[0]['group'],'demo')
            self.assertNotIn('cmdline',rows[0])
            self.assertNotIn('must not',json.dumps(rows))

    def test_pid_reuse_and_counter_reset_stay_unknown(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'sys/kernel/random').mkdir(parents=True)
            (root/'sys/kernel/random/boot_id').write_text('boot')
            state=root/'state.json'
            state.write_text(json.dumps({'time':10,'boot':'boot','disks':{'sda':[2048,4096,500]},'processes':{'42':[100,1]}}))
            row={'pid':42,'name':'new','state':'R','ticks':200,'start':2,'cpu_time':2,'memory':100,'group':'system'}
            with patch.object(mobile,'PROC',root),patch.object(mobile,'STATE',state),patch.object(mobile,'process_snapshot',return_value=[row]),patch.object(mobile,'disk_counters',return_value={'sda':[1024,2048,100]}),patch.object(mobile.time,'monotonic',return_value=13):
                rows,rates=mobile.sample()
            self.assertIsNone(rows[0]['cpu'])
            self.assertEqual(rates,{})
            self.assertNotIn('ticks',rows[0])
            self.assertNotIn('start',rows[0])
            self.assertEqual(state.stat().st_mode&0o777,0o600)

    def test_cpu_and_disk_deltas(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'sys/kernel/random').mkdir(parents=True)
            (root/'sys/kernel/random/boot_id').write_text('boot')
            state=root/'state.json';state.write_text(json.dumps({'time':10,'boot':'boot','disks':{'sda':[0,0,0]},'processes':{'42':[100,1]}}))
            row={'pid':42,'name':'same','state':'R','ticks':400,'start':1,'cpu_time':4,'memory':100,'group':'system'}
            with patch.object(mobile,'PROC',root),patch.object(mobile,'STATE',state),patch.object(mobile,'process_snapshot',return_value=[row]),patch.object(mobile,'disk_counters',return_value={'sda':[3072,6144,1500]}),patch.object(mobile.time,'monotonic',return_value=13),patch.object(mobile.os,'sysconf',return_value=100):
                rows,rates=mobile.sample()
            self.assertEqual(rows[0]['cpu'],100)
            self.assertEqual(rates['sda'],{'read':1024,'write':2048,'busy':50})

if __name__=='__main__':unittest.main(verbosity=2)
