"""Small fnOS CGI application. Secrets and HA calls stay on the NAS."""
import contextlib
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import time
import urllib.error
import urllib.request

FAN = 'fan.cabinet'
TEMP = 'sensor.cabinet_temperature'
AUTOMATIONS = ('weak_box_fan_speed_schedule', 'weak_box_fan_temperature_cooldown')
HA_URL = 'http://127.0.0.1:8123/api/'

class AppError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status

class HomeAssistant:
    def __init__(self, token):
        self.token = token

    def request(self, path, data=None):
        req = urllib.request.Request(HA_URL + path,
            data=None if data is None else json.dumps(data).encode(),
            headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise AppError('Home Assistant 授权失效，请在连接设置中更新令牌。', 502) from None
            raise AppError('Home Assistant 未完成请求，请刷新状态后重试。', 502) from None
        except (OSError, ValueError):
            raise AppError('暂时无法连接 Home Assistant，请确认它正在运行。', 503) from None

    def service(self, domain, service, data):
        return self.request('services/' + domain + '/' + service, data)

class Controller:
    def __init__(self, directory, ha_factory=HomeAssistant):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.factory = ha_factory

    def config(self):
        try:
            return json.loads((self.directory / 'connection.json').read_text())
        except FileNotFoundError:
            return {}
        except (ValueError, OSError):
            raise AppError('连接配置无法读取，请重新设置。', 503) from None

    @contextlib.contextmanager
    def locked(self):
        fd = os.open(self.directory / 'control.lock', os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def secret(self):
        with self.locked():
            path = self.directory / 'csrf-secret'
            if not path.exists():
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, 'w') as file:
                    file.write(secrets.token_hex(32))
            return path.read_bytes()

    def csrf(self):
        timestamp = str(int(time.time()))
        signature = hmac.new(self.secret(), timestamp.encode(), hashlib.sha256).hexdigest()
        return timestamp + '.' + signature

    def check_csrf(self, value):
        try:
            timestamp, signature = value.split('.', 1)
            age = time.time() - int(timestamp)
            expected = hmac.new(self.secret(), timestamp.encode(), hashlib.sha256).hexdigest()
            return 0 <= age <= 43200 and hmac.compare_digest(signature, expected)
        except (ValueError, AttributeError):
            return False

    def ha(self):
        token = self.config().get('token')
        if not token:
            raise AppError('请先连接本机 Home Assistant。', 409)
        return self.factory(token)

    def entities(self, states, config=None):
        fan_id = (self.config() if config is None else config).get("fan_entity", FAN)
        all_states = {s['entity_id']: s for s in states}
        automations = {s.get('attributes', {}).get('id'): s for s in states
                       if s['entity_id'].startswith('automation.')}
        if fan_id not in all_states:
            raise AppError('Home Assistant 中未找到弱电箱风扇。', 409)
        if not all(key in automations for key in AUTOMATIONS):
            raise AppError('未找到已部署的温控自动化，请先恢复弱电箱温控策略。', 409)
        return all_states, [automations[key] for key in AUTOMATIONS]

    def snapshot(self, ha=None):
        if not self.config().get('token') and ha is None:
            return {'configured': False}
        states, autos = self.entities((ha or self.ha()).request('states'))
        config = self.config()
        fan, temp = states[config.get('fan_entity', FAN)], states.get(config.get('temperature_entity', TEMP), {})
        flags = [a['state'] == 'on' for a in autos]
        mode = 'auto' if all(flags) else 'manual' if not any(flags) else 'mixed'
        available = fan['state'] in ('on', 'off')
        speed = fan.get('attributes', {}).get('percentage')
        speed = int(speed) if isinstance(speed, (int, float)) else None
        temperature = None
        try:
            temperature = float(temp['state'])
            if not -40 <= temperature <= 125:
                temperature = None
        except (KeyError, TypeError, ValueError):
            pass
        return {'configured': True, 'fan_entity': config.get('fan_entity', FAN),
                'temperature_entity': config.get('temperature_entity', TEMP), 'available': available, 'on': fan['state'] == 'on',
                'speed': speed, 'voltage': round(2.5 + (max(1, speed)-1)/99*2.5, 2)
                    if speed is not None and fan['state'] == 'on' else 0 if fan['state'] == 'off' else None,
                'temperature': temperature, 'temperature_updated': temp.get('last_updated'),
                'mode': mode, 'automation_running': [a.get('attributes', {}).get('current', 0) for a in autos],
                'updated_at': int(time.time())}

    def connect(self, data):
        if not {'token'} <= set(data) or set(data) - {'token', 'fan_entity', 'temperature_entity'} or not isinstance(data['token'], str) or not 20 <= len(data['token'].strip()) <= 8192:
            raise AppError('请输入有效的 Home Assistant 长期访问令牌。')
        token = data['token'].strip()
        if '\n' in token or '\r' in token:
            raise AppError('令牌不能包含换行。')
        import re
        settings = {key: data.get(key, self.config().get(key, default)) for key, default in
                    [('fan_entity', FAN), ('temperature_entity', TEMP)]}
        for key, value in settings.items():
            domain = 'fan' if key == 'fan_entity' else 'sensor'
            if not isinstance(value, str) or not re.fullmatch(domain + r'\.[a-z0-9_]+', value):
                raise AppError('设备实体 ID 格式无效。')
        ha = self.factory(token)
        states = ha.request('states')
        if not any(item.get('entity_id') == settings['fan_entity'] for item in states):
            raise AppError('Home Assistant 中未找到指定风扇。', 409)
        self.entities(states, settings)
        if not any(item.get('entity_id') == settings['temperature_entity'] for item in states):
            raise AppError('Home Assistant 中未找到指定温度传感器。', 409)
        with self.locked():
            path = self.directory / 'connection.json'
            tmp = self.directory / ('connection-' + secrets.token_hex(6) + '.tmp')
            fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            try:
                with os.fdopen(fd, 'w') as file:
                    json.dump({'token': token, **settings}, file)
                    file.flush()
                    os.fsync(file.fileno())
                tmp.replace(path)
            finally:
                tmp.unlink(missing_ok=True)
        return self.snapshot(ha)

    def control(self, data):
        action = data.get('action')
        if action not in ('auto', 'manual', 'speed', 'off'):
            raise AppError('不支持的操作。')
        if set(data) != ({'action', 'speed'} if action == 'speed' else {'action'}):
            raise AppError('操作参数无效。')
        speed = data.get('speed')
        if action == 'speed' and (type(speed) is not int or not 1 <= speed <= 100):
            raise AppError('转速必须是 1–100 的整数。')
        with self.locked():
            ha = self.ha()
            states, autos = self.entities(ha.request('states'))
            fan_id = self.config().get('fan_entity', FAN)
            if action != 'auto' and states[fan_id]['state'] not in ('on', 'off'):
                raise AppError('风扇当前离线，操作未执行。', 409)
            ids = [a['entity_id'] for a in autos]
            original_on = [a['entity_id'] for a in autos if a['state'] == 'on']
            original_off = [a['entity_id'] for a in autos if a['state'] != 'on']
            try:
                if action == 'auto':
                    ha.service('automation', 'turn_on', {'entity_id': ids})
                    ha.service('automation', 'trigger', {'entity_id': ids[0], 'skip_condition': False})
                else:
                    # Stop an in-flight 10-minute cooldown before applying manual control.
                    ha.service('automation', 'turn_off', {'entity_id': ids, 'stop_actions': True})
                    if action != 'manual':
                        ha.service('fan', 'turn_on' if action == 'speed' else 'turn_off',
                                   {'entity_id': fan_id, **({'percentage': speed} if action == 'speed' else {})})
            except AppError as exc:
                try:
                    if original_on:
                        ha.service('automation', 'turn_on', {'entity_id': original_on})
                    if original_off:
                        ha.service('automation', 'turn_off', {'entity_id': original_off, 'stop_actions': True})
                    if ids[0] in original_on:
                        ha.service('automation', 'trigger', {'entity_id': ids[0], 'skip_condition': False})
                except AppError:
                    raise AppError('操作未完成，恢复自动化状态也失败。请立即在 Home Assistant 检查风扇。', 502) from None
                raise AppError(str(exc) + ' 已恢复操作前的自动化开关状态，请刷新确认风扇。', exc.status) from None
            return self.snapshot(ha)
