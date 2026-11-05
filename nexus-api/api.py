#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nexus API — API order akun VPN milik sendiri untuk AutoscriptXRAY
(fork Aethernal07/AutoscriptXRAY) di VPS user.

Pengganti API NadiaVPN: bot toko (atau script apa pun) memesan akun
VMess/VLESS/Trojan ke server SENDIRI, tanpa reseller, tanpa potongan
saldo pihak ketiga, tanpa payment gateway.

Desain:
- Python stdlib murni (http.server), tanpa pip install apa pun.
- Default bind 127.0.0.1:8788 — hanya bisa diakses dari VPS itu sendiri
  (bot toko jalan di VPS yang sama). JANGAN bind 0.0.0.0 kecuali paham
  risikonya; bila suatu saat perlu akses luar, taruh di belakang
  reverse proxy HTTPS (Caddy/Nginx) dan tetap pakai token.
- Auth: header `Authorization: Bearer <API_TOKEN>` dari
  /etc/nexus-api/config.env (atau env NEXUS_API_CONFIG).
- Pembuatan akun memakai script resmi Autoscript yang sama persis
  dengan panelbot: /etc/autoscriptvpn/xray/add-<proto>.sh
  (stdin: username, masa aktif dalam hari).
- Idempotent per (protocol, username): order ulang username yang sama
  mengembalikan hasil order pertama (tersimpan di state JSON),
  tidak membuat akun dobel — sama seperti perilaku API Nadia.

Endpoint:
  GET  /api/v1/health            -> status, domain, jumlah akun
  GET  /api/v1/accounts          -> daftar akun dari *.db Xray
  POST /api/v1/vpn/order         -> buat akun
       Body (kompatibel Nadia):
         {"server_id": "nexus-1", "protocol": "vmess",
          "type": "month", "duration": 1, "username": "buyer1"}
       type: month = 30 hari, week = 7 hari, day = 1 hari (x duration)
       Body (mode langsung):
         {"protocol": "vmess", "days": 30, "username": "buyer1",
          "quota_gb": 100}        # quota_gb opsional (butuh panelbot)
       Respons:
         {"success": true, "data": {"username": ..., "uuid": ...,
          "host": ..., "expired": "YYYY-MM-DD", "link": ...,
          "links": [...], "protocol": ..., "days": ...}}
"""

import base64
import hmac
import json
import os
import re
import subprocess
import sys
import threading
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CONFIG_PATH = os.environ.get("NEXUS_API_CONFIG", "/etc/nexus-api/config.env")
STATE_DIR_DEFAULT = "/var/lib/nexus-api"

# protocol -> (script, db file, link prefix)
PROTOCOLS = {
    "vmess": ("add-vmess.sh", "vmess.db", "vmess://"),
    "vless": ("add-vless.sh", "vless.db", "vless://"),
    "trojan": ("add-trojan.sh", "trojan.db", "trojan://"),
}
TYPE_DAYS = {"month": 30, "week": 7, "day": 1}
USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{3,32}$")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
MAX_BODY = 16 * 1024

CREATE_LOCK = threading.Lock()


def load_config():
    cfg = {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    # env menimpa file (berguna untuk tes)
    for k in ("API_TOKEN", "BIND_HOST", "BIND_PORT", "SERVER_ID",
              "SCRIPT_DIR", "DB_DIR", "DOMAIN_FILE", "STATE_DIR",
              "PANELBOT_DIR"):
        if os.environ.get("NEXUS_" + k):
            cfg[k] = os.environ["NEXUS_" + k]
    return cfg


CFG = load_config()
API_TOKEN = CFG.get("API_TOKEN", "")
BIND_HOST = CFG.get("BIND_HOST", "127.0.0.1")
BIND_PORT = int(CFG.get("BIND_PORT", "8788"))
SERVER_ID = CFG.get("SERVER_ID", "nexus-1")
SCRIPT_DIR = CFG.get("SCRIPT_DIR", "/etc/autoscriptvpn/xray")
DB_DIR = CFG.get("DB_DIR", "/etc/xray")
DOMAIN_FILE = CFG.get("DOMAIN_FILE", "/etc/xray/domain")
STATE_DIR = CFG.get("STATE_DIR", STATE_DIR_DEFAULT)
PANELBOT_DIR = CFG.get("PANELBOT_DIR", "/opt/panelbot")
STATE_FILE = os.path.join(STATE_DIR, "orders.json")


# ------------------------------------------------------------------ state

def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def save_state(state):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)
    os.replace(tmp, STATE_FILE)


# ------------------------------------------------------------------ xray

def db_lookup(proto, username):
    """Cari user di db Xray -> (exp, uuid) atau None."""
    _, dbname, _ = PROTOCOLS[proto]
    try:
        with open(os.path.join(DB_DIR, dbname), "r",
                  encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 3 and parts[0] == username:
                    return parts[1], parts[2]
    except FileNotFoundError:
        pass
    return None


def db_all():
    out = []
    for proto, (_, dbname, _) in PROTOCOLS.items():
        try:
            with open(os.path.join(DB_DIR, dbname), "r",
                      encoding="utf-8", errors="replace") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        out.append({"protocol": proto,
                                    "username": parts[0],
                                    "expired": parts[1]})
        except FileNotFoundError:
            continue
    return out


def get_domain():
    try:
        with open(DOMAIN_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def set_quota(username, quota_gb):
    """Pakai modul quota panelbot bila ada. quota_gb None = unlimited."""
    if quota_gb is None:
        quota_bytes = None
    else:
        quota_bytes = int(quota_gb) * 1000 * 1000 * 1000
    try:
        if PANELBOT_DIR not in sys.path:
            sys.path.insert(0, PANELBOT_DIR)
        import quota_state  # modul panelbot di /opt/panelbot
        quota_state.set_quota(username, quota_bytes)
        return True
    except Exception:
        return False


def create_account(proto, username, days, quota_gb=None):
    """Jalankan add-<proto>.sh non-interaktif. Return dict data akun."""
    script = os.path.join(SCRIPT_DIR, PROTOCOLS[proto][0])
    prefix = PROTOCOLS[proto][2]
    link_re = re.compile(re.escape(prefix) + r"[A-Za-z0-9+/=_:@.\-]+")
    try:
        proc = subprocess.run(
            ["bash", script],
            input=f"{username}\n{days}\n",
            capture_output=True, text=True, timeout=180,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Timeout: script pembuatan akun > 180 detik.")
    out = ANSI_RE.sub("", (proc.stdout or "") + "\n" + (proc.stderr or ""))
    if "already exists" in out.lower():
        raise ValueError(f"Username '{username}' sudah dipakai.")
    links, seen = [], set()
    for m in link_re.findall(out):
        if m not in seen:
            seen.add(m)
            links.append(m)
    rec = db_lookup(proto, username)
    if rec is None and not links:
        tail = "\n".join(out.strip().splitlines()[-5:])
        raise RuntimeError(f"Akun tidak terbentuk. Output script:\n{tail}")
    exp = rec[0] if rec else (date.today() + timedelta(days=days)).isoformat()
    uuid = rec[1] if rec else ""
    quota_ok = set_quota(username, quota_gb) if quota_gb is not None else None
    data = {
        "username": username,
        "protocol": proto,
        "uuid": uuid,
        "host": get_domain(),
        "expired": exp,
        "days": days,
        "link": links[0] if links else "",
        "links": links,
    }
    if quota_ok is not None:
        data["quota_gb"] = quota_gb if quota_ok else None
        data["quota_applied"] = quota_ok
    return data


# ------------------------------------------------------------------ http

class Handler(BaseHTTPRequestHandler):
    server_version = "NexusAPI/1.0"

    def log_message(self, fmt, *args):  # jangan log token/header
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authed(self):
        hdr = self.headers.get("Authorization", "")
        token = hdr[7:] if hdr.startswith("Bearer ") else ""
        return bool(API_TOKEN) and hmac.compare_digest(token, API_TOKEN)

    def do_GET(self):
        if not self._authed():
            return self._json(401, {"success": False, "error": "unauthorized"})
        if self.path == "/api/v1/health":
            return self._json(200, {"success": True, "data": {
                "status": "ok", "server_id": SERVER_ID,
                "domain": get_domain(), "accounts": len(db_all())}})
        if self.path == "/api/v1/accounts":
            return self._json(200, {"success": True, "data": db_all()})
        return self._json(404, {"success": False, "error": "not found"})

    def do_POST(self):
        if self.path != "/api/v1/vpn/order":
            return self._json(404, {"success": False, "error": "not found"})
        if not self._authed():
            return self._json(401, {"success": False, "error": "unauthorized"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY:
            return self._json(400, {"success": False,
                                    "error": "body tidak valid"})
        try:
            req = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return self._json(400, {"success": False, "error": "JSON rusak"})
        if not isinstance(req, dict):
            return self._json(400, {"success": False, "error": "JSON rusak"})

        username = str(req.get("username", "")).strip()
        proto = str(req.get("protocol", "vmess")).lower().strip()
        if not USERNAME_RE.match(username):
            return self._json(400, {"success": False, "error":
                                    "username 3-32 karakter [A-Za-z0-9_-]"})
        if proto not in PROTOCOLS:
            return self._json(400, {"success": False, "error":
                                    f"protocol harus salah satu: "
                                    f"{', '.join(PROTOCOLS)}"})
        sid = req.get("server_id")
        if sid is not None and str(sid) != SERVER_ID:
            return self._json(400, {"success": False, "error":
                                    f"server_id tidak dikenal: {sid}"})
        # masa aktif: mode langsung (days) atau mode Nadia (type+duration)
        if req.get("days") is not None:
            try:
                days = int(req["days"])
            except (TypeError, ValueError):
                return self._json(400, {"success": False,
                                        "error": "days harus angka"})
        else:
            typ = str(req.get("type", "month")).lower().strip()
            if typ not in TYPE_DAYS:
                return self._json(400, {"success": False, "error":
                                        "type harus month/week/day"})
            try:
                dur = int(req.get("duration", 1))
            except (TypeError, ValueError):
                return self._json(400, {"success": False,
                                        "error": "duration harus angka"})
            days = TYPE_DAYS[typ] * dur
        if days < 1 or days > 365:
            return self._json(400, {"success": False,
                                    "error": "masa aktif 1-365 hari"})
        quota_gb = req.get("quota_gb")
        if quota_gb is not None:
            try:
                quota_gb = int(quota_gb)
                if quota_gb < 0 or quota_gb > 10240:
                    raise ValueError
            except (TypeError, ValueError):
                return self._json(400, {"success": False,
                                        "error": "quota_gb tidak valid"})

        key = f"{proto}:{username}"
        with CREATE_LOCK:
            state = load_state()
            if key in state:
                data = dict(state[key])
                data["idempotent_replay"] = True
                return self._json(200, {"success": True, "data": data})
            try:
                data = create_account(proto, username, days, quota_gb)
            except ValueError as e:
                return self._json(409, {"success": False, "error": str(e)})
            except RuntimeError as e:
                return self._json(500, {"success": False, "error": str(e)})
            state[key] = data
            save_state(state)
        return self._json(201, {"success": True, "data": data})


def main():
    if len(API_TOKEN) < 24:
        print("API_TOKEN kosong/terlalu pendek (<24). Isi dulu "
              f"{CONFIG_PATH}", file=sys.stderr)
        return 1
    srv = ThreadingHTTPServer((BIND_HOST, BIND_PORT), Handler)
    print(f"Nexus API jalan di http://{BIND_HOST}:{BIND_PORT} "
          f"(server_id={SERVER_ID})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
