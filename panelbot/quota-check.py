#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pengecek kuota VMess untuk panelbot AutoscriptXRAY.

Dijalankan berkala oleh systemd timer (quota-check.timer, tiap 5 menit):

1. Baca counter trafik per user dari API Xray (StatsService):
     xray api statsquery --server=127.0.0.1:10085
   Counter Xray adalah angka kumulatif sejak proses Xray start dan
   kembali ke 0 setiap Xray restart; script ini menyimpan snapshot
   counter terakhir dan hanya menambahkan DELTA ke pemakaian terakumulasi
   di quota-state.json, jadi restart Xray tidak menghapus riwayat pakai.
2. Bila pemakaian user melewati kuotanya:
   - client user itu dikeluarkan dari semua inbound di /etc/xray/config.json
     (backup dibuat dulu, config divalidasi `xray -test`, rollback bila gagal),
   - baris user dihapus dari /etc/xray/vmess.db,
   - Xray di-restart,
   - pemilik server diberi tahu lewat Telegram (token + ID dari
     /etc/panelbot/config.env).

Bila API Xray tidak bisa dihubungi (statistik belum diaktifkan),
script keluar diam-diam tanpa menyentuh apa pun (hanya mencatat sekali
ke /var/lib/panelbot/quota-api-warned).
"""

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quota_state  # noqa: E402

CONFIG_ENV = "/etc/panelbot/config.env"
XRAY_CONFIG = "/etc/xray/config.json"
VMESS_DB = "/etc/xray/vmess.db"
API_SERVER = "127.0.0.1:10085"
WARN_MARKER = "/var/lib/panelbot/quota-api-warned"


def xray_bin():
    p = shutil.which("xray")
    if p:
        return p
    for cand in ("/usr/local/bin/xray", "/usr/bin/xray"):
        if os.path.exists(cand):
            return cand
    return "xray"


def query_stats():
    """Return {email: (up, down)} atau None bila API tidak menjawab."""
    try:
        proc = subprocess.run(
            [xray_bin(), "api", "statsquery", f"--server={API_SERVER}", "-reset=false"],
            capture_output=True, text=True, timeout=30,
        )
    except Exception:
        return None
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if "traffic>>>" not in text:
        return None
    stats = {}
    # Format utama: JSON protobuf {"stat":[{"name":"user>>>e>>>traffic>>>uplink","value":"123"}]}
    try:
        data = json.loads(proc.stdout)
        for entry in data.get("stat", []):
            name = entry.get("name", "")
            m = re.match(r"user>>>(.+)>>>traffic>>>(uplink|downlink)$", name)
            if m:
                cur = stats.setdefault(m.group(1), [0, 0])
                cur[0 if m.group(2) == "uplink" else 1] = int(entry.get("value", 0))
        if stats:
            return {k: tuple(v) for k, v in stats.items()}
    except Exception:
        pass
    # Fallback: pola regex longgar
    for m in re.finditer(
        r'user>>>(.+?)>>>traffic>>>(uplink|downlink)"\s*,\s*"value":\s*"?(\\d+)"?', text
    ):
        cur = stats.setdefault(m.group(1), [0, 0])
        cur[0 if m.group(2) == "uplink" else 1] = int(m.group(3))
    if stats:
        return {k: tuple(v) for k, v in stats.items()}
    return {}


def load_env():
    cfg = {}
    try:
        with open(CONFIG_ENV, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    ids = []
    for part in cfg.get("ALLOWED_IDS", "").split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    return cfg.get("BOT_TOKEN", ""), ids


def notify(text):
    token, ids = load_env()
    if not token or not ids:
        return
    for chat_id in ids:
        try:
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=20).read()
        except Exception as e:
            print(f"notify gagal: {e}", file=sys.stderr)


def remove_user_everywhere(username):
    """Keluarkan user dari config Xray + vmess.db, validasi, restart. Return bool."""
    try:
        with open(XRAY_CONFIG, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        print(f"tidak bisa baca config: {e}", file=sys.stderr)
        return False

    changed = False
    for inbound in cfg.get("inbounds", []):
        clients = (inbound.get("settings") or {}).get("clients")
        if isinstance(clients, list):
            kept = [c for c in clients if c.get("email") != username]
            if len(kept) != len(clients):
                inbound["settings"]["clients"] = kept
                changed = True
    if not changed:
        return True  # memang sudah tidak ada

    backup = XRAY_CONFIG + ".bak-quota"
    shutil.copy2(XRAY_CONFIG, backup)
    tmp = XRAY_CONFIG + ".tmp-quota"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, XRAY_CONFIG)

    test = subprocess.run(
        [xray_bin(), "-test", "-config", XRAY_CONFIG],
        capture_output=True, text=True, timeout=30,
    )
    if test.returncode != 0:
        shutil.copy2(backup, XRAY_CONFIG)
        print(f"xray -test gagal, config dikembalikan: {test.stderr[-300:]}", file=sys.stderr)
        return False

    # hapus dari database akun
    try:
        with open(VMESS_DB, "r", encoding="utf-8") as f:
            lines = f.readlines()
        with open(VMESS_DB, "w", encoding="utf-8") as f:
            for line in lines:
                if not line.split() or line.split()[0] != username:
                    f.write(line)
    except FileNotFoundError:
        pass

    subprocess.run(["systemctl", "restart", "xray"], timeout=60)
    return True


def main():
    stats = query_stats()
    if stats is None:
        if not os.path.exists(WARN_MARKER):
            os.makedirs(os.path.dirname(WARN_MARKER), exist_ok=True)
            with open(WARN_MARKER, "w", encoding="utf-8") as f:
                f.write(datetime.now().isoformat())
            print(
                "API Xray tidak menjawab di "
                + API_SERVER
                + " — statistik per user belum aktif? Jalankan enable-stats.sh sekali. "
                "Pengecekan kuota dilewati.",
                file=sys.stderr,
            )
        return
    if os.path.exists(WARN_MARKER):
        try:
            os.unlink(WARN_MARKER)
        except OSError:
            pass

    exceeded = []

    def _account(data):
        for user, rec in data.items():
            quota = rec.get("quota")
            if quota is None or rec.get("disabled"):
                continue
            up, down = stats.get(user, (0, 0))
            last_up = int(rec.get("last_up", 0))
            last_down = int(rec.get("last_down", 0))
            d_up = up if up < last_up else up - last_up
            d_down = down if down < last_down else down - last_down
            rec["used"] = int(rec.get("used", 0)) + d_up + d_down
            rec["last_up"] = up
            rec["last_down"] = down
            if rec["used"] >= quota:
                exceeded.append((user, rec["used"], quota))

    quota_state.update(_account)

    for user, used, quota in exceeded:
        if remove_user_everywhere(user):
            def _mark(data, u=user):
                if u in data:
                    data[u]["disabled"] = True
            quota_state.update(_mark)
            notify(
                "⛔ Kuota habis — akun dinonaktifkan\n"
                f"User : {user}\n"
                f"Pakai: {quota_state.fmt_bytes(used)} / {quota_state.fmt_bytes(quota)}"
            )
            print(f"kuota habis: {user} ({used}/{quota}) — akun dinonaktifkan")
        else:
            print(f"GAGAL menonaktifkan {user}; dicoba lagi pada cek berikutnya", file=sys.stderr)


if __name__ == "__main__":
    main()
