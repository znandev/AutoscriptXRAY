#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tes offline Nexus API: script Autoscript & db Xray dipalsukan di
folder temp, server API asli dijalankan, lalu endpoint-nya ditembak
pakai HTTP beneran. Tidak menyentuh VPS / Xray sama sekali."""

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 18788
BASE = f"http://127.0.0.1:{PORT}"
TOKEN = "test-token-1234567890abcdef"

FAKE_SCRIPT = """#!/bin/bash
read -r user
read -r days
DB="$(dirname "$0")/../../xray/vmess.db"
mkdir -p "$(dirname "$DB")"
if grep -q "^$user " "$DB" 2>/dev/null; then
  echo "user already exists"
  exit 0
fi
echo "$user 2026-12-31 11111111-2222-3333-4444-555555555555" >> "$DB"
LINK="vmess://eyJ2IjoiMiIsInBzIjoidGVzdCJ9"
echo "--- VMess WS TLS ---"
echo "$LINK"
"""


def call(method, path, token=None, payload=None):
    req = urllib.request.Request(BASE + path, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=10) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def main():
    tmp = tempfile.mkdtemp(prefix="nexus-api-test-")
    script_dir = os.path.join(tmp, "autoscript", "xray")
    db_dir = os.path.join(tmp, "xray")
    os.makedirs(script_dir)
    os.makedirs(db_dir)
    with open(os.path.join(script_dir, "add-vmess.sh"), "w") as f:
        f.write(FAKE_SCRIPT)
    domain_file = os.path.join(db_dir, "domain")
    with open(domain_file, "w") as f:
        f.write("vpn.contoh.my.id\n")

    env = dict(os.environ)
    env.update({
        "NEXUS_API_TOKEN": TOKEN,
        "NEXUS_BIND_HOST": "127.0.0.1",
        "NEXUS_BIND_PORT": str(PORT),
        "NEXUS_SERVER_ID": "nexus-1",
        "NEXUS_SCRIPT_DIR": script_dir,
        "NEXUS_DB_DIR": db_dir,
        "NEXUS_DOMAIN_FILE": domain_file,
        "NEXUS_STATE_DIR": os.path.join(tmp, "state"),
        "NEXUS_PANELBOT_DIR": os.path.join(tmp, "no-panelbot"),
    })
    proc = subprocess.Popen(
        [sys.executable, os.path.join(HERE, "api.py")],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True)
    checks = []
    try:
        for _ in range(50):
            try:
                code, _ = call("GET", "/api/v1/health", token=TOKEN)
                break
            except Exception:
                time.sleep(0.2)
        else:
            raise RuntimeError("server tidak naik")

        def check(name, cond):
            checks.append((name, bool(cond)))
            print(("PASS " if cond else "FAIL ") + name)

        code, res = call("GET", "/api/v1/health")
        check("health tanpa token = 401", code == 401)

        code, res = call("GET", "/api/v1/health", token="salah-token")
        check("health token salah = 401", code == 401)

        code, res = call("GET", "/api/v1/health", token=TOKEN)
        check("health ok + domain terbaca",
              code == 200 and res["data"]["domain"] == "vpn.contoh.my.id")

        code, res = call("POST", "/api/v1/vpn/order", token=TOKEN, payload={
            "server_id": "nexus-1", "protocol": "vmess", "type": "month",
            "duration": 1, "username": "buyer1"})
        d = res.get("data", {})
        check("order Nadia-style 30 hari = 201",
              code == 201 and res.get("success") is True)
        check("order: days=30, exp & uuid dari db",
              d.get("days") == 30 and d.get("expired") == "2026-12-31"
              and d.get("uuid", "").startswith("11111111"))
        check("order: host & link vmess ada",
              d.get("host") == "vpn.contoh.my.id"
              and d.get("link", "").startswith("vmess://"))

        code, res = call("POST", "/api/v1/vpn/order", token=TOKEN, payload={
            "server_id": "nexus-1", "protocol": "vmess", "type": "month",
            "duration": 1, "username": "buyer1"})
        check("order ulang = idempotent replay (200, tidak dobel)",
              code == 200 and res["data"].get("idempotent_replay") is True)

        code, res = call("POST", "/api/v1/vpn/order", token=TOKEN, payload={
            "protocol": "vmess", "days": 7, "username": "buyer2"})
        check("order mode days=7 = 201",
              code == 201 and res["data"]["days"] == 7)

        code, res = call("POST", "/api/v1/vpn/order", token=TOKEN, payload={
            "protocol": "vmess", "days": 7, "username": "nama jelek!"})
        check("username ilegal = 400", code == 400)

        code, res = call("POST", "/api/v1/vpn/order", token=TOKEN, payload={
            "server_id": "server-orang", "protocol": "vmess",
            "days": 7, "username": "buyer3"})
        check("server_id asing = 400", code == 400)

        code, res = call("POST", "/api/v1/vpn/order", token=TOKEN, payload={
            "protocol": "wireguard", "days": 7, "username": "buyer3"})
        check("protocol tak dikenal = 400", code == 400)

        code, res = call("GET", "/api/v1/accounts", token=TOKEN)
        names = {a["username"] for a in res.get("data", [])}
        check("daftar akun berisi buyer1+buyer2",
              code == 200 and names == {"buyer1", "buyer2"})
    finally:
        proc.terminate()
        try:
            out, _ = proc.communicate(timeout=5)
        except Exception:
            proc.kill()
            out = ""
    failed = [n for n, ok in checks if not ok]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} cek lulus")
    if failed:
        print("GAGAL:", failed)
        print(out[-2000:])
        return 1
    print("SEMUA TES LULUS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
