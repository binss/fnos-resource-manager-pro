#!/usr/bin/python3
import json
import os
from pathlib import Path
import sys
import secrets
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from fan_controller import AppError, Controller
import fan_native as native_fnos


def main():
    app = Controller(str(Path(os.environ.get('TRIM_PKGVAR', '/var/apps/resmonpro/var')) / 'fan'))
    method = os.environ.get('REQUEST_METHOD', 'GET')
    path = urlsplit(os.environ.get('REQUEST_URI', '/')).path.partition('index.cgi/fan')[2] or '/'
    static = {'/': ('index.html', 'text/html; charset=utf-8'),
              '/app.js': ('app.js', 'application/javascript; charset=utf-8'),
              '/style.css': ('style.css', 'text/css; charset=utf-8')}
    status, mime = 200, 'application/json; charset=utf-8'
    nonce = secrets.token_urlsafe(24)
    try:
        if method in ('GET', 'HEAD') and path in static:
            name, mime = static[path]
            body = (ROOT / 'ui/fan' / name).read_bytes()
            if path == '/':
                body = body.replace(b'__CSRF__', app.csrf().encode())
                try:
                    imports = native_fnos.import_map()
                    # Verify native compatibility before exposing its module to the page.
                    native_fnos.module()
                    script = '<script type="importmap" nonce="' + nonce + '">' + imports + '</script>'
                    body = body.replace(b'<!--FNOS_IMPORT_MAP-->', script.encode())
                except (ValueError, OSError):
                    body = body.replace(b'<!--FNOS_IMPORT_MAP-->', b'')
        elif method in ('GET', 'HEAD') and path == '/api/fnos-native.js':
            try:
                body, mime = native_fnos.module().encode(), 'application/javascript; charset=utf-8'
            except (ValueError, OSError):
                raise AppError('当前飞牛版本暂不兼容原生风扇面板，请使用系统设置。', 409) from None
        elif method in ('GET', 'HEAD') and path == '/api/state':
            body = json.dumps(app.snapshot(), ensure_ascii=False).encode()
        elif method == 'POST' and path in ('/api/control', '/api/connect'):
            if not app.check_csrf(os.environ.get('HTTP_X_FAN_CSRF', '')):
                raise AppError('页面授权已过期，请刷新后重试。', 403)
            if os.environ.get('CONTENT_TYPE', '').split(';')[0].strip() != 'application/json':
                raise AppError('需要 JSON 请求。', 415)
            n = int(os.environ.get('CONTENT_LENGTH', '0') or '0')
            if not 0 < n <= 12000:
                raise AppError('请求大小无效。', 413)
            raw = sys.stdin.buffer.read(n)
            if len(raw) != n:
                raise AppError('请求不完整。')
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise AppError('请求格式无效。')
            result = app.connect(data) if path == '/api/connect' else app.control(data)
            body = json.dumps(result, ensure_ascii=False).encode()
        else:
            raise AppError('未找到此接口。', 404)
    except AppError as exc:
        status, body = exc.status, json.dumps({'error': str(exc)}, ensure_ascii=False).encode()
    except (ValueError, UnicodeError):
        status, body = 400, '{"error":"请求格式无效。"}'.encode()
    except Exception:
        status, body = 503, '{"error":"应用暂不可用，请稍后刷新或检查连接设置。"}'.encode()
    headers = (f'Status: {status}\r\nContent-Type: {mime}\r\nCache-Control: no-store\r\n'
               'X-Content-Type-Options: nosniff\r\nReferrer-Policy: no-referrer\r\n'
               f"Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-{nonce}'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'self'\r\n\r\n")
    sys.stdout.buffer.write(headers.encode())
    if method != 'HEAD':
        sys.stdout.buffer.write(body)

if __name__ == '__main__':
    main()
