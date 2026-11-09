import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'packages/resmonpro/app'))
from fan_controller import Controller, AppError, FAN, TEMP, AUTOMATIONS

class FakeHA:
    def __init__(self):
        self.calls=[];self.fail_fan=False
        self.states=[{'entity_id':FAN,'state':'on','attributes':{'percentage':30}},
                     {'entity_id':TEMP,'state':'38.2','last_updated':'2026-11-09T03:20:00Z','attributes':{}}]
        self.states += [{'entity_id':'automation.'+a,'state':'on','attributes':{'id':a}} for a in AUTOMATIONS]
    def request(self,path):
        assert path=='states'
        return self.states
    def service(self,domain,service,data):
        self.calls.append((domain,service,data))
        if domain=='fan':
            if self.fail_fan:raise AppError('test fan failure',502)
            self.states[0]['state']='on' if service=='turn_on' else 'off'
            self.states[0]['attributes']['percentage']=data.get('percentage',0)
        if domain=='automation' and service in ('turn_on','turn_off'):
            for s in self.states:
                if s['entity_id'] in data['entity_id']:s['state']='on' if service=='turn_on' else 'off'

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.ha=FakeHA()
        self.app=Controller(self.temp.name,lambda token:self.ha)
        self.app.connect({'token':'dummy-testing-token-which-is-not-real'})
    def tearDown(self):self.temp.cleanup()
    def test_token_not_in_snapshot_and_private_storage(self):
        s=self.app.snapshot();self.assertEqual(s['mode'],'auto');self.assertAlmostEqual(s['voltage'],3.23)
        self.assertNotIn('token',json.dumps(s));self.assertEqual(os.stat(Path(self.temp.name)/'connection.json').st_mode&0o777,0o600)
    def test_manual_speed_cancels_cooldown_before_fan(self):
        s=self.app.control({'action':'speed','speed':60})
        self.assertEqual(s['mode'],'manual');self.assertEqual(s['speed'],60)
        self.assertEqual(self.ha.calls[0][0:2],('automation','turn_off'));self.assertTrue(self.ha.calls[0][2]['stop_actions'])
    def test_manual_mode_keeps_fan_untouched(self):
        s=self.app.control({'action':'manual'});self.assertEqual(s['mode'],'manual');self.assertEqual(s['speed'],30)
        self.assertFalse(any(c[0]=='fan' for c in self.ha.calls))
    def test_auto_enables_both_and_triggers_controller(self):
        self.app.control({'action':'manual'});self.ha.calls=[]
        s=self.app.control({'action':'auto'});self.assertEqual(s['mode'],'auto')
        self.assertEqual(self.ha.calls[-1][0:2],('automation','trigger'))
        self.assertEqual(len(self.ha.calls[0][2]['entity_id']),2)
    def test_off_pauses_auto(self):
        s=self.app.control({'action':'off'});self.assertFalse(s['on']);self.assertEqual(s['mode'],'manual');self.assertEqual(s['voltage'],0)
    def test_failure_restores_previous_automations(self):
        self.ha.fail_fan=True
        with self.assertRaises(AppError):self.app.control({'action':'speed','speed':60})
        self.assertEqual(self.app.snapshot()['mode'],'auto')
    def test_invalid_speed_has_no_side_effects(self):
        for n in [0,101,True,1.5,'30',None]:
            with self.assertRaises(AppError):self.app.control({'action':'speed','speed':n})
        self.assertEqual(self.ha.calls,[])
    def test_offline_blocks_manual_control(self):
        self.ha.states[0]['state']='unavailable'
        with self.assertRaises(AppError):self.app.control({'action':'speed','speed':30})
        self.assertEqual(self.ha.calls,[])
    def test_csrf_tamper_rejected(self):
        t=self.app.csrf();self.assertTrue(self.app.check_csrf(t));self.assertFalse(self.app.check_csrf(t+'0'));self.assertFalse(self.app.check_csrf(''))
    def test_mixed_mode_detected(self):
        self.ha.states[-1]['state']='off';self.assertEqual(self.app.snapshot()['mode'],'mixed')
    def test_unknown_temperature_not_zero(self):
        self.ha.states[1]['state']='unavailable';self.assertIsNone(self.app.snapshot()['temperature'])
    def test_connection_rejects_missing_sensor_without_replacing_config(self):
        before=(Path(self.temp.name)/'connection.json').read_bytes()
        with self.assertRaises(AppError):
            self.app.connect({'token':'dummy-new-token-for-testing-only','temperature_entity':'sensor.missing'})
        self.assertEqual((Path(self.temp.name)/'connection.json').read_bytes(),before)
    def test_custom_entities_and_invalid_id(self):
        self.ha.states[0]['entity_id']='fan.test_cabinet'
        self.ha.states[1]['entity_id']='sensor.test_temperature'
        result=self.app.connect({'token':'dummy-testing-token-which-is-not-real','fan_entity':'fan.test_cabinet','temperature_entity':'sensor.test_temperature'})
        self.assertEqual(result['fan_entity'],'fan.test_cabinet')
        self.assertEqual(self.app.control({'action':'speed','speed':60})['speed'],60)
        for value in ['light.example','fan../bad',None]:
            with self.assertRaises(AppError):
                self.app.connect({'token':'dummy-testing-token-which-is-not-real','fan_entity':value})
    def test_cgi_blocks_untrusted_posts_and_traversal(self):
        cgi=Path(__file__).resolve().parents[1]/'packages/resmonpro/app/ui/index.cgi'
        for method,uri,body,status in [('POST','/api/control',b'{"action":"off"}',403),('GET','/../controller.py',b'',404)]:
            env={**os.environ,'TRIM_PKGVAR':self.temp.name,'REQUEST_METHOD':method,'REQUEST_URI':'/cgi/ThirdParty/resmonpro/index.cgi/fan'+uri,'CONTENT_LENGTH':str(len(body)),'CONTENT_TYPE':'application/json'}
            p=subprocess.run([sys.executable,str(cgi)],input=body,capture_output=True,env=env)
            self.assertTrue(p.stdout.startswith(('Status: '+str(status)).encode()),p.stdout)

if __name__=='__main__':unittest.main()
