#!/usr/bin/python3
"""Serve the panel through the fnOS authenticated application gateway."""
import json
import os
from pathlib import Path
import sqlite3
import sys
from urllib.parse import parse_qs, urlsplit
from urllib.request import urlopen
from urllib.error import HTTPError

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from monitor import live, query, recent
import native

path = urlsplit(os.environ.get("REQUEST_URI", "")).path.partition("index.cgi")[2] or "/"
method = os.environ.get("REQUEST_METHOD", "GET")
status, mime = "200 OK", "application/json"
static = {"/temperature/device-aliases.json": ("device-aliases.json", "application/json; charset=utf-8"),
          "/temperature/": ("temperature.html", "text/html; charset=utf-8"),
          "/basic": ("index.html", "text/html; charset=utf-8"),
          "/panel.js": ("panel.js", "application/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8")}
try:
    if method not in ("GET", "HEAD"):
        status, body = "405 Method Not Allowed", b'{"error":"Method not allowed"}'
    elif path == "/":
        print("Status: 302 Found\r\nLocation: " + native.ENTRY + "/native\r\nCache-Control: no-store\r\n\r\n", end="")
        raise SystemExit
    elif path == "/native":
        mime = "text/html; charset=utf-8"
        if all((native.WEB / "assets" / name).is_file() for name in native.ASSETS.values()):
            body = native.page().encode()
        else:
            body = (root / "ui" / "index.html").read_bytes()
    elif path.startswith("/native/") and path.removeprefix("/native/") in native.ASSETS:
        mime = "application/javascript; charset=utf-8"
        body = native.module(path.removeprefix("/native/")).encode()
    elif path == "/native/history.js":
        mime = "application/javascript; charset=utf-8"
        body = (root / "ui" / "history.js").read_bytes()
    elif path in static:
        file, mime = static[path]
        body = (root / "ui" / file).read_bytes()
    elif path == "/temperature":
        print("Status: 302 Found\r\nLocation: " + native.ENTRY + "/temperature/\r\nCache-Control: no-store\r\n\r\n", end="")
        raise SystemExit
    elif path.startswith("/temperature/api/"):
        route = path.removeprefix("/temperature")
        if route not in ("/api/current", "/api/history", "/api/storage", "/api/daily", "/api/export.csv"):
            status, body = "404 Not Found", b'{"error":"Not found"}'
        else:
            query_string = os.environ.get("QUERY_STRING", "") if route in ("/api/history", "/api/daily", "/api/export.csv") else ""
            try:
                with urlopen("http://127.0.0.1:39188" + route + ("?" + query_string if query_string else ""), timeout=10) as response:
                    mime = response.headers.get("Content-Type", "application/json")
                    body = response.read()
            except HTTPError as error:
                status = str(error.code) + " " + error.reason
                mime, body = "application/json", b'{"error":"Temperature request failed"}'
            except OSError:
                status, body = "503 Service Unavailable", '{"error":"温度采集服务暂不可用，请在应用中心重新启动资源管理 Pro"}'.encode()
    elif path == "/api/recent":
        body = json.dumps(recent()).encode()
    elif path == "/api/live":
        body = json.dumps(live()).encode()
    elif path == "/api/history":
        params = parse_qs(os.environ.get("QUERY_STRING", ""))
        body = json.dumps(query(int(params.get("hours", ["24"])[0]))).encode()
    else:
        status, body = "404 Not Found", b'{"error":"Not found"}'
except (ValueError, KeyError):
    status, body = "400 Bad Request", b'{"error":"Invalid range"}'
except (OSError, sqlite3.Error):
    status, body = "503 Service Unavailable", b'{"error":"Data unavailable"}'

disposition = "Content-Disposition: attachment; filename=temperature-daily.csv\r\n" if path == "/temperature/api/export.csv" and status == "200 OK" else ""
sys.stdout.buffer.write(f"{disposition}Status: {status}\r\nContent-Type: {mime}\r\n"
                        "Cache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\n\r\n".encode())
if method != "HEAD":
    sys.stdout.buffer.write(body)
