#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Panel Bot Telegram untuk AutoscriptXRAY (fork Aethernal07/AutoscriptXRAY).

Fitur:
- Buat akun VMess (tombol masa aktif 7/15/30 hari atau custom,
  lalu tombol kuota 100 GB / 500 GB / 1 TB / unlimited)
- Status server (uptime, RAM, disk, service Xray/NGINX, jumlah akun)
- Daftar akun VMess + pemakaian kuota

Kuota ditegakkan oleh quota-check.py (systemd timer, 5 menit) yang
membaca statistik trafik per user dari API Xray dan menonaktifkan
akun yang melewati kuotanya. State bersama bot <-> checker ada di
quota_state.py (/var/lib/panelbot/quota-state.json).

Hanya memakai library standar Python 3 (tanpa pip install).
Token bot dan allowlist ID Telegram dibaca dari /etc/panelbot/config.env
(file itu diisi manual di VPS, JANGAN commit token ke repo).

Bot memanggil script bawaan AutoscriptXRAY yang sudah terinstall:
  /etc/autoscriptvpn/xray/add-vmess.sh  (input stdin: username, expired-days)
Database akun dibaca dari /etc/xray/vmess.db (format: user exp uuid).
"""

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quota_state  # noqa: E402

CONFIG_PATH = os.environ.get("PANELBOT_CONFIG", "/etc/panelbot/config.env")
ADD_VMESS = "/etc/autoscriptvpn/xray/add-vmess.sh"
VMESS_DB = "/etc/xray/vmess.db"
DOMAIN_FILE = "/etc/xray/domain"
STATE_DIR = "/var/lib/panelbot"
OFFSET_FILE = os.path.join(STATE_DIR, "offset.txt")

USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,30}$")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
VMESS_LINK_RE = re.compile(r"vmess://[A-Za-z0-9+/=_-]+")


# ---------------------------------------------------------------- config
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
        print(f"Config tidak ditemukan: {CONFIG_PATH}", file=sys.stderr)
    token = cfg.get("BOT_TOKEN", "")
    allowed = set()
    for part in cfg.get("ALLOWED_IDS", "").split(","):
        part = part.strip()
        if part.isdigit():
            allowed.add(int(part))
    return token, allowed


BOT_TOKEN, ALLOWED_IDS = load_config()
API = f"https://api.telegram.org/bot{BOT_TOKEN}/"


# ---------------------------------------------------------------- telegram api
def api(method, payload=None, timeout=65):
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        API + method, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def send(chat_id, text, markup=None):
    payload = {"chat_id": chat_id, "text": text}
    if markup:
        payload["reply_markup"] = markup
    try:
        api("sendMessage", payload, timeout=30)
    except Exception as e:  # jangan sampai bot mati gara-gara satu pesan gagal
        print(f"sendMessage gagal: {e}", file=sys.stderr)


def answer_callback(cb_id):
    try:
        api("answerCallbackQuery", {"callback_query_id": cb_id}, timeout=15)
    except Exception:
        pass


def main_menu_markup():
    return {
        "inline_keyboard": [
            [{"text": "🆕 Buat Akun VMess", "callback_data": "mk"}],
            [
                {"text": "📊 Status Server", "callback_data": "st"},
                {"text": "📋 Daftar Akun", "callback_data": "ls"},
            ],
        ]
    }


def days_markup():
    return {
        "inline_keyboard": [
            [
                {"text": "7 hari", "callback_data": "d:7"},
                {"text": "15 hari", "callback_data": "d:15"},
                {"text": "30 hari", "callback_data": "d:30"},
            ],
            [
                {"text": "✏️ Custom", "callback_data": "d:custom"},
                {"text": "❌ Batal", "callback_data": "d:cancel"},
            ],
        ]
    }


def quota_markup():
    return {
        "inline_keyboard": [
            [
                {"text": "100 GB", "callback_data": "q:100"},
                {"text": "500 GB", "callback_data": "q:500"},
                {"text": "1 TB", "callback_data": "q:1024"},
            ],
            [
                {"text": "♾️ Unlimited", "callback_data": "q:0"},
                {"text": "❌ Batal", "callback_data": "d:cancel"},
            ],
        ]
    }


# ---------------------------------------------------------------- helpers
def clean_ansi(text):
    return ANSI_RE.sub("", text or "")


def db_lookup(username):
    """Cari user di /etc/xray/vmess.db -> (exp, uuid) atau None."""
    try:
        with open(VMESS_DB, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 3 and parts[0] == username:
                    return parts[1], parts[2]
    except FileNotFoundError:
        pass
    return None


def db_all():
    users = []
    try:
        with open(VMESS_DB, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    users.append((parts[0], parts[1]))
    except FileNotFoundError:
        pass
    return users


def label_link(link):
    """Beri label link vmess: WS TLS / WS NTLS / gRPC."""
    try:
        raw = link[len("vmess://"):]
        raw += "=" * (-len(raw) % 4)
        cfg = json.loads(base64.b64decode(raw).decode("utf-8", "replace"))
        net = str(cfg.get("net", ""))
        port = str(cfg.get("port", ""))
        tls = str(cfg.get("tls", ""))
        if net == "grpc":
            return "VMess gRPC (TLS 443)"
        if port == "443" or tls == "tls":
            return "VMess WS TLS (443)"
        return "VMess WS NTLS (80)"
    except Exception:
        return "VMess"


def create_vmess(username, days, quota_bytes=None):
    """Jalankan add-vmess.sh secara non-interaktif. Return (ok, pesan)."""
    try:
        proc = subprocess.run(
            ["bash", ADD_VMESS],
            input=f"{username}\n{days}\n",
            capture_output=True,
            text=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        return False, "Timeout: script pembuatan akun tidak selesai dalam 180 detik."
    except Exception as e:
        return False, f"Gagal menjalankan script: {e}"

    out = clean_ansi((proc.stdout or "") + "\n" + (proc.stderr or ""))
    if "already exists" in out.lower():
        return False, f"Username '{username}' sudah dipakai. Coba nama lain."

    links = []
    seen = set()
    for m in VMESS_LINK_RE.findall(out):
        if m not in seen:
            seen.add(m)
            links.append(m)

    rec = db_lookup(username)
    if not links and rec is None:
        tail = "\n".join(out.strip().splitlines()[-5:])
        return False, f"Akun tidak terbentuk. Cuplikan output script:\n{tail}"

    quota_state.set_quota(username, quota_bytes)
    exp = rec[0] if rec else (date.today() + timedelta(days=days)).isoformat()
    lines = [
        "✅ Akun VMess dibuat",
        f"Remarks : {username}",
        f"Expired : {exp} ({days} hari)",
        f"Kuota   : {quota_state.fmt_bytes(quota_bytes)}",
    ]
    dom = ""
    try:
        with open(DOMAIN_FILE, "r", encoding="utf-8") as f:
            dom = f.read().strip()
    except FileNotFoundError:
        pass
    if dom:
        lines.append(f"Domain  : {dom}")
    if links:
        lines.append("")
        for lk in links:
            lines.append(f"— {label_link(lk)} —")
            lines.append(lk)
            lines.append("")
    else:
        lines.append("(Link tidak tertangkap dari output; cek manual di VPS.)")
    return True, "\n".join(lines).strip()


def human_uptime():
    try:
        with open("/proc/uptime", "r", encoding="utf-8") as f:
            secs = int(float(f.read().split()[0]))
    except Exception:
        return "-"
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    parts = []
    if d:
        parts.append(f"{d} hari")
    if h:
        parts.append(f"{h} jam")
    parts.append(f"{m} menit")
    return " ".join(parts)


def service_state(name):
    try:
        p = subprocess.run(
            ["systemctl", "is-active", name], capture_output=True, text=True, timeout=10
        )
        return "🟢 ONLINE" if p.stdout.strip() == "active" else "🔴 " + (p.stdout.strip() or "unknown")
    except Exception:
        return "⚪ tidak diketahui"


def server_status():
    lines = ["📊 STATUS SERVER", f"Uptime : {human_uptime()}"]
    # RAM dari /proc/meminfo (KB)
    try:
        mem = {}
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                k, v = line.split(":", 1)
                mem[k.strip()] = int(v.split()[0])
        total = mem.get("MemTotal", 0) // 1024
        avail = mem.get("MemAvailable", 0) // 1024
        used = total - avail
        lines.append(f"RAM    : {used}MB / {total}MB")
    except Exception:
        pass
    try:
        du = shutil.disk_usage("/")
        used_g = du.used / (1024 ** 3)
        total_g = du.total / (1024 ** 3)
        lines.append(f"Disk   : {used_g:.1f}G / {total_g:.0f}G")
    except Exception:
        pass
    lines.append(f"Xray   : {service_state('xray')}")
    lines.append(f"NGINX  : {service_state('nginx')}")
    users = db_all()
    lines.append(f"Akun VMess terdaftar: {len(users)}")
    try:
        with open(DOMAIN_FILE, "r", encoding="utf-8") as f:
            lines.append(f"Domain : {f.read().strip()}")
    except FileNotFoundError:
        pass
    return "\n".join(lines)


def account_list():
    users = db_all()
    if not users:
        return "Belum ada akun VMess terdaftar."
    snap = quota_state.snapshot()
    lines = [f"📋 DAFTAR AKUN VMESS ({len(users)})"]
    for i, (u, exp) in enumerate(users[:50], 1):
        rec = snap.get(u)
        if rec is None:
            q = ""
        elif rec.get("disabled"):
            q = " — ⛔ nonaktif (kuota habis)"
        elif rec.get("quota") is None:
            q = " — kuota ∞"
        else:
            q = (
                f" — {quota_state.fmt_bytes(rec.get('used', 0))}"
                f"/{quota_state.fmt_bytes(rec.get('quota'))}"
            )
        lines.append(f"{i}. {u} — exp {exp}{q}")
    if len(users) > 50:
        lines.append(f"… dan {len(users) - 50} akun lain")
    return "\n".join(lines)


# ---------------------------------------------------------------- bot flow
# state per chat: {"step": "username"|"days_custom", "user": "<nama>"}
STATES = {}


def handle_message(msg):
    chat = msg.get("chat", {})
    frm = msg.get("from", {})
    chat_id = chat.get("id")
    user_id = frm.get("id")
    text = (msg.get("text") or "").strip()
    if chat_id is None or user_id is None:
        return
    if chat.get("type") != "private":
        return
    if user_id not in ALLOWED_IDS:
        return  # diam ke orang asing

    if text.startswith("/start") or text.startswith("/menu"):
        STATES.pop(chat_id, None)
        send(chat_id, "Panel AutoscriptXRAY. Pilih menu:", main_menu_markup())
        return

    st = STATES.get(chat_id)
    if st and st.get("step") == "username":
        if not USERNAME_RE.match(text):
            send(chat_id, "Username tidak valid. Gunakan huruf/angka/strip/garis-bawah, 1–30 karakter. Coba lagi:")
            return
        st = {"step": "days", "user": text}
        STATES[chat_id] = st
        send(chat_id, f"Username: {text}\nPilih masa aktif:", days_markup())
        return

    if st and st.get("step") == "days_custom":
        if not text.isdigit() or not (1 <= int(text) <= 365):
            send(chat_id, "Masukkan angka hari antara 1–365:")
            return
        st["days"] = int(text)
        st["step"] = "quota"
        STATES[chat_id] = st
        send(chat_id, f"Masa aktif: {text} hari\nPilih batas kuota akun:", quota_markup())
        return

    send(chat_id, "Pilih menu:", main_menu_markup())


def handle_callback(cb):
    cb_id = cb.get("id")
    msg = cb.get("message", {})
    frm = cb.get("from", {})
    chat = msg.get("chat", {})
    chat_id = chat.get("id")
    user_id = frm.get("id")
    data = cb.get("data") or ""
    if chat_id is None or user_id is None:
        return
    if user_id not in ALLOWED_IDS:
        answer_callback(cb_id)
        return
    answer_callback(cb_id)

    if data == "mk":
        STATES[chat_id] = {"step": "username"}
        send(chat_id, "Ketik username untuk akun VMess baru:")
        return
    if data == "st":
        send(chat_id, server_status(), main_menu_markup())
        return
    if data == "ls":
        send(chat_id, account_list(), main_menu_markup())
        return
    if data.startswith("d:"):
        st = STATES.get(chat_id)
        if not st or "user" not in st:
            send(chat_id, "Sesi pembuatan akun sudah berakhir. Mulai lagi dari menu:", main_menu_markup())
            return
        choice = data[2:]
        if choice == "cancel":
            STATES.pop(chat_id, None)
            send(chat_id, "Dibatalkan.", main_menu_markup())
            return
        if choice == "custom":
            st["step"] = "days_custom"
            STATES[chat_id] = st
            send(chat_id, "Ketik masa aktif dalam hari (1–365):")
            return
        days = int(choice)
        st["days"] = days
        st["step"] = "quota"
        STATES[chat_id] = st
        send(chat_id, f"Masa aktif: {days} hari\nPilih batas kuota akun:", quota_markup())
        return
    if data.startswith("q:"):
        st = STATES.get(chat_id)
        if not st or "user" not in st or "days" not in st:
            send(chat_id, "Sesi pembuatan akun sudah berakhir. Mulai lagi dari menu:", main_menu_markup())
            return
        gb = int(data[2:])
        quota_bytes = None if gb == 0 else gb * quota_state.GB
        username = st["user"]
        days = st["days"]
        STATES.pop(chat_id, None)
        send(
            chat_id,
            f"⏳ Membuat akun '{username}' ({days} hari, kuota {quota_state.fmt_bytes(quota_bytes)})…",
        )
        ok, pesan = create_vmess(username, days, quota_bytes)
        send(chat_id, pesan, main_menu_markup() if ok else None)
        return


# ---------------------------------------------------------------- polling
def load_offset():
    try:
        with open(OFFSET_FILE, "r", encoding="utf-8") as f:
            return int(f.read().strip() or 0)
    except Exception:
        return 0


def save_offset(off):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(OFFSET_FILE, "w", encoding="utf-8") as f:
            f.write(str(off))
    except Exception:
        pass


def main():
    if not BOT_TOKEN:
        print("BOT_TOKEN kosong. Isi dulu /etc/panelbot/config.env", file=sys.stderr)
        sys.exit(1)
    if not ALLOWED_IDS:
        print("ALLOWED_IDS kosong. Isi dulu /etc/panelbot/config.env", file=sys.stderr)
        sys.exit(1)
    offset = load_offset()
    print("Panel bot jalan. Menunggu pesan...", flush=True)
    while True:
        try:
            res = api("getUpdates", {"offset": offset, "timeout": 50}, timeout=60)
            for upd in res.get("result", []):
                offset = upd["update_id"] + 1
                save_offset(offset)
                try:
                    if "message" in upd:
                        handle_message(upd["message"])
                    elif "callback_query" in upd:
                        handle_callback(upd["callback_query"])
                except Exception as e:
                    print(f"handler error: {e}", file=sys.stderr)
        except urllib.error.URLError as e:
            print(f"getUpdates gagal: {e}", file=sys.stderr)
            time.sleep(5)
        except Exception as e:
            print(f"loop error: {e}", file=sys.stderr)
            time.sleep(3)


if __name__ == "__main__":
    main()
