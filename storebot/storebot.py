#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot Toko VPN (publik) untuk AutoscriptXRAY.

Fitur:
- Registrasi pengguna otomatis, kartu info (ID, status, saldo, transaksi)
- Buat akun VMess potong saldo (durasi x kuota, harga dari prices.json)
- Trial gratis 1x per pengguna
- TopUp manual: pengguna transfer ke pembayaran admin, admin setujui/tolak
  dari notifikasi bot, saldo terisi otomatis saat disetujui
- Akun Saya (sisa hari + pemakaian kuota, berbagi state dengan panelbot)
- Perpanjang (perpanjang tanggal di vmess.db), Hapus Akun
- Riwayat transaksi, status Reseller (harga khusus), menu Bantuan
- Admin: buka/tutup tiap menu, setujui topup & reseller, kredit saldo manual

Hanya memakai Python standard library. Data di SQLite.
"""

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import traceback
import urllib.parse
import urllib.request
from datetime import date, timedelta

CONFIG_PATH = os.environ.get("STOREBOT_CONFIG", "/etc/storebot/config.env")
PRICES_PATH = os.environ.get("STOREBOT_PRICES", "/etc/storebot/prices.json")
DB_PATH = os.environ.get("STOREBOT_DB", "/var/lib/storebot/store.db")
QUOTA_STATE = "/var/lib/panelbot/quota-state.json"

ADD_VMESS = "/etc/autoscriptvpn/xray/add-vmess.sh"
VMESS_DB = "/etc/xray/vmess.db"
XRAY_CONFIG = "/etc/xray/config.json"

GB = 1000 ** 3


def load_env(path):
    cfg = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return cfg


CFG = load_env(CONFIG_PATH)
BOT_TOKEN = CFG.get("BOT_TOKEN", "")
ADMIN_IDS = {int(x) for x in re.split(r"[,\s]+", CFG.get("ADMIN_IDS", "")) if x.isdigit()}
PAYMENT_INFO = CFG.get("PAYMENT_INFO", "Hubungi admin untuk info pembayaran.").replace("\\n", "\n")
SHOP_NAME = CFG.get("SHOP_NAME", "Nexus Vpn")

if not BOT_TOKEN:
    print("BOT_TOKEN belum diisi di", CONFIG_PATH, file=sys.stderr)
    sys.exit(1)

API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ---------------------------------------------------------------- database

db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.row_factory = sqlite3.Row
db.executescript(
    """
    CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY,
        username TEXT, first_name TEXT,
        status TEXT DEFAULT 'user',
        saldo INTEGER DEFAULT 0,
        trial_used INTEGER DEFAULT 0,
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, vpn_user TEXT, days INTEGER,
        quota_bytes INTEGER, price INTEGER,
        created_at TEXT, expires TEXT,
        kind TEXT DEFAULT 'order', active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS tx(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, type TEXT, amount INTEGER,
        note TEXT, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS topups(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, amount INTEGER,
        status TEXT DEFAULT 'pending', created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS settings(
        key TEXT PRIMARY KEY, value TEXT
    );
    """
)
db.commit()

DEFAULT_SETTINGS = {
    "order_open": "1", "topup_open": "1", "trial_open": "1",
    "renew_open": "1", "delete_open": "1",
}
for k, v in DEFAULT_SETTINGS.items():
    db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
db.commit()


def setting(key):
    row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else "1"


def set_setting(key, value):
    db.execute("INSERT INTO settings(key,value) VALUES(?,?) "
               "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    db.commit()


def get_user(uid):
    return db.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()


def ensure_user(msg):
    u = msg["from"]
    uid = u["id"]
    if not get_user(uid):
        db.execute(
            "INSERT INTO users(user_id, username, first_name, status, saldo, trial_used, created_at)"
            " VALUES(?,?,?,?,0,0,?)",
            (uid, u.get("username", ""), u.get("first_name", ""), "user",
             date.today().isoformat()),
        )
        db.commit()
    return get_user(uid)


def add_tx(uid, typ, amount, note):
    db.execute("INSERT INTO tx(user_id,type,amount,note,created_at) VALUES(?,?,?,?,?)",
               (uid, typ, amount, note, date.today().isoformat()))
    db.commit()


def tx_count(uid):
    row = db.execute("SELECT COUNT(*) c FROM tx WHERE user_id=?", (uid,)).fetchone()
    return row["c"]


# ---------------------------------------------------------------- prices

def load_prices():
    with open(PRICES_PATH, encoding="utf-8") as f:
        return json.load(f)


def quota_labels(prices):
    return list(prices["kuota"].keys())


def price_for(prices, user, days, qlabel):
    base = prices["harga"][str(days)][qlabel]
    if user["status"] == "reseller":
        disc = int(prices.get("diskon_reseller_persen", 0))
        return base * (100 - disc) // 100
    return base


def rp(n):
    return "Rp" + f"{int(n):,}".replace(",", ".")


def fmt_quota(b):
    if b is None:
        return "∞"
    return f"{b / GB:.0f} GB" if b >= GB else f"{b / 1e6:.0f} MB"


# ---------------------------------------------------------------- telegram

def tg(method, params):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(f"{API}/{method}", data=data)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def send(chat_id, text, markup=None):
    params = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
              "disable_web_page_preview": "true"}
    if markup:
        params["reply_markup"] = json.dumps(markup)
    try:
        tg("sendMessage", params)
    except Exception:
        traceback.print_exc()


def edit(chat_id, msg_id, text, markup=None):
    params = {"chat_id": chat_id, "message_id": msg_id, "text": text,
              "parse_mode": "HTML", "disable_web_page_preview": "true"}
    if markup:
        params["reply_markup"] = json.dumps(markup)
    try:
        tg("editMessageText", params)
    except Exception:
        pass  # pesan sama / sudah berubah


def answer_cb(cb_id, text=""):
    try:
        tg("answerCallbackQuery", {"callback_query_id": cb_id, "text": text})
    except Exception:
        pass


def kb(rows):
    return {"inline_keyboard": rows}


def btn(text, data):
    return {"text": text, "callback_data": data}


# ---------------------------------------------------------------- xray side

ANSI = re.compile(r"\x1b\[[0-9;]*m")
USER_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{2,19}$")


def vmess_db():
    out = {}
    try:
        with open(VMESS_DB, encoding="utf-8", errors="replace") as f:
            for line in f:
                p = line.split()
                if len(p) >= 3:
                    out[p[0]] = (p[1], p[2])
    except FileNotFoundError:
        pass
    return out


def set_quota(username, quota_bytes):
    """Tulis kuota ke state bersama panelbot (dibaca quota-check)."""
    sys.path.insert(0, "/opt/panelbot")
    try:
        import quota_state
        quota_state.set_quota(username, quota_bytes)
    except Exception:
        traceback.print_exc()


def create_vmess(username, days):
    proc = subprocess.run([ADD_VMESS], input=f"{username}\n{days}\n",
                          capture_output=True, text=True, timeout=120)
    out = ANSI.sub("", (proc.stdout or "") + (proc.stderr or ""))
    links = re.findall(r"vmess://\S+", out)
    if not links:
        raise RuntimeError("script tidak menghasilkan link")
    labels = []
    for link in links:
        try:
            pad = link[8:] + "=" * (-len(link[8:]) % 4)
            cfg = json.loads(__import__("base64").urlsafe_b64decode(pad))
            net = cfg.get("net", "")
            tls = cfg.get("tls", "")
            if net == "grpc":
                labels.append(("gRPC", link))
            elif tls == "tls":
                labels.append(("WS TLS (443)", link))
            else:
                labels.append(("WS Non-TLS (80)", link))
        except Exception:
            labels.append(("VMess", link))
    exp = vmess_db().get(username, ("", ""))[0]
    return labels, exp


def renew_vmess(username, extra_days):
    lines = []
    done = False
    newexp = ""
    with open(VMESS_DB, encoding="utf-8") as f:
        raw = f.read().splitlines()
    for line in raw:
        p = line.split()
        if len(p) >= 3 and p[0] == username and not done:
            try:
                cur = date.fromisoformat(p[1])
            except ValueError:
                cur = date.today()
            base = max(cur, date.today())
            newexp = (base + timedelta(days=extra_days)).isoformat()
            line = f"{p[0]} {newexp} {p[2]}"
            done = True
        lines.append(line)
    if not done:
        raise RuntimeError("akun tidak ditemukan di vmess.db")
    with open(VMESS_DB, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return newexp


def delete_vmess(username):
    with open(XRAY_CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    removed = False
    for inbound in cfg.get("inbounds", []):
        st = inbound.get("settings", {})
        clients = st.get("clients")
        if isinstance(clients, list):
            keep = [c for c in clients if c.get("email") != username]
            if len(keep) != len(clients):
                removed = True
            st["clients"] = keep
    if removed:
        tmp = XRAY_CONFIG + ".new.json"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=1)
        test = subprocess.run(["xray", "-test", "-config", tmp],
                              capture_output=True, text=True, timeout=60)
        if test.returncode != 0:
            os.unlink(tmp)
            raise RuntimeError("validasi config gagal, akun tidak dihapus")
        os.replace(tmp, XRAY_CONFIG)
        subprocess.run(["systemctl", "restart", "xray"], timeout=60)
    # hapus dari vmess.db
    try:
        with open(VMESS_DB, encoding="utf-8") as f:
            lines = f.read().splitlines()
        lines = [ln for ln in lines if not (ln.split() and ln.split()[0] == username)]
        with open(VMESS_DB, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except FileNotFoundError:
        pass
    return removed


def quota_usage(username):
    try:
        with open(QUOTA_STATE, encoding="utf-8") as f:
            st = json.load(f)
        rec = st.get("users", {}).get(username)
        if rec:
            return rec.get("used", 0)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------- menus

states = {}  # chat_id -> (step, data)


def closed(key):
    return setting(key) != "1"


def main_menu(user):
    def lbl(base, key):
        return ("❌ " + base + " Ditutup") if closed(key) else base
    rows = [
        [btn(lbl("🛒 Buat Akun", "order_open"), "m:order"),
         btn(lbl("♻️ Perpanjang", "renew_open"), "m:renew")],
        [btn(lbl("🎁 Trial", "trial_open"), "m:trial"),
         btn(lbl("💳 TopUp", "topup_open"), "m:topup")],
        [btn("👤 Akun Saya", "m:myacc"),
         btn(lbl("🗑 Hapus Akun", "delete_open"), "m:delete")],
        [btn("📊 Riwayat", "m:history"), btn("🤝 Jadi Reseller", "m:reseller")],
        [btn("🆘 Bantuan", "m:help")],
    ]
    if user["user_id"] in ADMIN_IDS:
        rows.append([btn("🛠 Panel Admin", "m:admin")])
    return kb(rows)


def info_card(user):
    status = "Reseller" if user["status"] == "reseller" else "Bukan Reseller"
    uname = "@" + user["username"] if user["username"] else "-"
    return (
        f"👋 <b>Selamat datang di {SHOP_NAME}</b>\n\n"
        "🔵 <b>INFORMASI PENGGUNA</b>\n"
        f"🆔 ID : <code>{user['user_id']}</code>\n"
        f"👤 User : {uname}\n"
        f"👑 Status : {status}\n"
        f"💰 Saldo : {rp(user['saldo'])}\n"
        f"📊 Transaksi : {tx_count(user['user_id'])}\n\n"
        "👇 Silakan pilih menu di bawah:"
    )


def back_row():
    return [btn("⬅️ Menu Utama", "m:home")]


# ---------------------------------------------------------------- user flows

def show_home(chat_id, user, msg_id=None):
    if msg_id:
        edit(chat_id, msg_id, info_card(user), main_menu(user))
    else:
        send(chat_id, info_card(user), main_menu(user))


def start_order(chat_id, user, msg_id):
    if closed("order_open"):
        answer_cb_global("Menu Buat Akun sedang ditutup admin.")
        return
    prices = load_prices()
    rows = [[btn(f"📅 {d} Hari", f"ord:dur:{d}")] for d in prices["durasi_hari"]]
    rows.append(back_row())
    edit(chat_id, msg_id, "🛒 <b>Buat Akun VMess</b>\nPilih durasi:", kb(rows))


_cb_answer = ""


def answer_cb_global(text):
    global _cb_answer
    _cb_answer = text


def pick_quota(chat_id, user, msg_id, days, purpose, acc_id=None):
    prices = load_prices()
    rows = []
    for q in quota_labels(prices):
        price = price_for(prices, user, days, q)
        rows.append([btn(f"{q} — {rp(price)}", f"{purpose}:q:{days}:{q}:{acc_id or ''}")])
    rows.append(back_row())
    edit(chat_id, msg_id,
         f"🛒 <b>Buat Akun / Perpanjang</b>\nDurasi: {days} hari\nPilih kuota:", kb(rows))


def ask_username(chat_id, user, msg_id, purpose, days, qlabel, acc_id=None):
    prices = load_prices()
    if purpose == "ord":
        price = price_for(prices, user, days, qlabel)
        states[chat_id] = ("username_order", {"days": days, "q": qlabel, "price": price})
        edit(chat_id, msg_id,
             f"📦 Paket: <b>{days} hari / {qlabel}</b>\n💰 Harga: <b>{rp(price)}</b>\n"
             f"💳 Saldo kamu: {rp(user['saldo'])}\n\n"
             "Kirim <b>username</b> untuk akun VPN-nya (huruf kecil/angka, 3–20 karakter):",
             kb([back_row()]))
    else:  # renew: username sudah ada dari akun
        row = db.execute("SELECT * FROM orders WHERE id=?", (acc_id,)).fetchone()
        price = price_for(prices, user, days, qlabel)
        rows = [[btn(f"✅ Ya, bayar {rp(price)}", f"ren:go:{acc_id}:{days}:{price}")], back_row()]
        edit(chat_id, msg_id,
             f"♻️ Perpanjang <b>{row['vpn_user']}</b> selama {days} hari\n"
             f"💰 Harga: <b>{rp(price)}</b>\n💳 Saldo kamu: {rp(user['saldo'])}",
             kb(rows))


def do_order(chat_id, user, username, days, qlabel, price):
    prices = load_prices()
    quota_b = prices["kuota"][qlabel]
    user = get_user(user["user_id"])
    if user["saldo"] < price:
        send(chat_id, f"Saldo tidak cukup. Saldo: {rp(user['saldo'])}, harga: {rp(price)}.\n"
                      "Silakan TopUp dulu.", main_menu(user))
        return
    if username in vmess_db():
        send(chat_id, "Username itu sudah dipakai. Kirim username lain:", None)
        states[chat_id] = ("username_order", {"days": days, "q": qlabel, "price": price})
        return
    send(chat_id, "⏳ Akun sedang dibuat...")
    try:
        links, exp = create_vmess(username, days)
    except Exception as e:
        send(chat_id, f"Gagal membuat akun: {e}", main_menu(get_user(user["user_id"])))
        return
    db.execute("UPDATE users SET saldo=saldo-? WHERE user_id=?", (price, user["user_id"]))
    db.execute(
        "INSERT INTO orders(user_id,vpn_user,days,quota_bytes,price,created_at,expires,kind,active)"
        " VALUES(?,?,?,?,?,?,?,?,1)",
        (user["user_id"], username, days, quota_b, price, date.today().isoformat(), exp, "order"))
    db.commit()
    add_tx(user["user_id"], "order", -price, f"VMess {username} {days}h {qlabel}")
    set_quota(username, quota_b)
    parts = [f"✅ <b>Akun VMess berhasil dibuat!</b>\n\n👤 Username: <code>{username}</code>\n"
             f"📅 Expired: {exp}\n📦 Kuota: {qlabel}\n"]
    for label, link in links:
        parts.append(f"<b>{label}</b>\n<code>{link}</code>\n")
    parts.append("Simpan baik-baik link di atas, jangan dibagikan.")
    send(chat_id, "\n".join(parts), main_menu(get_user(user["user_id"])))


def do_trial(chat_id, user, msg_id):
    if closed("trial_open"):
        answer_cb_global("Menu Trial sedang ditutup admin.")
        return
    if user["trial_used"]:
        edit(chat_id, msg_id, "🎁 Trial gratis hanya bisa dipakai 1x per pengguna, dan kamu sudah memakainya.",
             kb([back_row()]))
        return
    states[chat_id] = ("username_trial", {})
    edit(chat_id, msg_id, "🎁 <b>Trial Gratis</b>\nKirim <b>username</b> untuk akun trial-nya "
                          "(huruf kecil/angka, 3–20 karakter):", kb([back_row()]))


def do_trial_create(chat_id, user, username):
    prices = load_prices()
    trial = prices.get("trial", {"hari": 1, "kuota_gb": 5})
    days = int(trial["hari"])
    quota_b = int(trial["kuota_gb"]) * GB
    if username in vmess_db():
        states[chat_id] = ("username_trial", {})
        send(chat_id, "Username itu sudah dipakai. Kirim username lain:")
        return
    send(chat_id, "⏳ Akun trial sedang dibuat...")
    try:
        links, exp = create_vmess(username, days)
    except Exception as e:
        send(chat_id, f"Gagal membuat akun trial: {e}", main_menu(get_user(user["user_id"])))
        return
    db.execute("UPDATE users SET trial_used=1 WHERE user_id=?", (user["user_id"],))
    db.execute(
        "INSERT INTO orders(user_id,vpn_user,days,quota_bytes,price,created_at,expires,kind,active)"
        " VALUES(?,?,?,?,0,?,?, 'trial',1)",
        (user["user_id"], username, days, quota_b, date.today().isoformat(), exp))
    db.commit()
    add_tx(user["user_id"], "trial", 0, f"Trial {username} {days}h")
    set_quota(username, quota_b)
    parts = [f"🎁 <b>Akun trial berhasil dibuat!</b>\n\n👤 Username: <code>{username}</code>\n"
             f"📅 Expired: {exp}\n📦 Kuota: {fmt_quota(quota_b)}\n"]
    for label, link in links:
        parts.append(f"<b>{label}</b>\n<code>{link}</code>\n")
    send(chat_id, "\n".join(parts), main_menu(get_user(user["user_id"])))


TOPUP_PRESETS = [10000, 25000, 50000, 100000]


def start_topup(chat_id, user, msg_id):
    if closed("topup_open"):
        answer_cb_global("Menu TopUp sedang ditutup admin.")
        return
    rows = [[btn(rp(a), f"top:amt:{a}")] for a in TOPUP_PRESETS]
    rows.append([btn("✏️ Nominal Lain", "top:custom")])
    rows.append(back_row())
    edit(chat_id, msg_id, "💳 <b>TopUp Saldo</b>\nPilih nominal:", kb(rows))


def topup_invoice(chat_id, user, msg_id, amount):
    rows = [[btn("✅ Saya Sudah Transfer", f"top:paid:{amount}")], back_row()]
    edit(chat_id, msg_id,
         f"💳 <b>TopUp {rp(amount)}</b>\n\nSilakan transfer ke:\n{PAYMENT_INFO}\n\n"
         f"Nominal: <b>{rp(amount)}</b>\n"
         "Setelah transfer, klik tombol di bawah. Saldo masuk setelah admin menyetujui.",
         kb(rows))


def topup_paid(chat_id, user, amount):
    cur = db.execute("INSERT INTO topups(user_id,amount,status,created_at) VALUES(?,?,'pending',?)",
                     (user["user_id"], amount, date.today().isoformat()))
    db.commit()
    tid = cur.lastrowid
    send(chat_id, "🧾 Permintaan topup kamu dicatat dan diteruskan ke admin. "
                  "Saldo akan masuk begitu disetujui.", main_menu(get_user(user["user_id"])))
    uname = "@" + user["username"] if user["username"] else user["first_name"]
    rows = [[btn("✅ Setujui", f"adm:topup_ok:{tid}"), btn("❌ Tolak", f"adm:topup_no:{tid}")]]
    for adm in ADMIN_IDS:
        send(adm, f"💳 <b>TopUp masuk</b>\nDari: {uname} (<code>{user['user_id']}</code>)\n"
                  f"Nominal: <b>{rp(amount)}</b>\nID topup: {tid}", kb(rows))


def my_accounts(chat_id, user, msg_id):
    rows_ = db.execute("SELECT * FROM orders WHERE user_id=? AND active=1 ORDER BY id DESC",
                       (user["user_id"],)).fetchall()
    if not rows_:
        edit(chat_id, msg_id, "👤 Kamu belum punya akun. Buat dari menu Buat Akun / Trial.",
             kb([back_row()]))
        return
    parts = ["👤 <b>Akun Saya</b>\n"]
    for o in rows_:
        used = quota_usage(o["vpn_user"])
        used_s = fmt_quota(used) if used is not None else "-"
        parts.append(f"• <code>{o['vpn_user']}</code> — exp {o['expires']}\n"
                     f"  Kuota: {used_s} / {fmt_quota(o['quota_bytes'])}")
    edit(chat_id, msg_id, "\n".join(parts), kb([back_row()]))


def pick_account(chat_id, user, msg_id, purpose):
    rows_ = db.execute("SELECT * FROM orders WHERE user_id=? AND active=1 ORDER BY id DESC",
                       (user["user_id"],)).fetchall()
    if not rows_:
        edit(chat_id, msg_id, "Kamu belum punya akun aktif.", kb([back_row()]))
        return
    rows = [[btn(f"{o['vpn_user']} (exp {o['expires']})", f"{purpose}:acc:{o['id']}")] for o in rows_]
    rows.append(back_row())
    title = "♻️ <b>Perpanjang</b>\nPilih akun:" if purpose == "ren" else "🗑 <b>Hapus Akun</b>\nPilih akun:"
    edit(chat_id, msg_id, title, kb(rows))


def do_renew(chat_id, user, acc_id, days, price):
    row = db.execute("SELECT * FROM orders WHERE id=? AND user_id=?", (acc_id, user["user_id"])).fetchone()
    if not row:
        return
    user = get_user(user["user_id"])
    if user["saldo"] < price:
        send(chat_id, f"Saldo tidak cukup. Saldo: {rp(user['saldo'])}, harga: {rp(price)}.",
             main_menu(user))
        return
    try:
        newexp = renew_vmess(row["vpn_user"], days)
    except Exception as e:
        send(chat_id, f"Gagal memperpanjang: {e}", main_menu(user))
        return
    db.execute("UPDATE users SET saldo=saldo-? WHERE user_id=?", (price, user["user_id"]))
    db.execute("UPDATE orders SET expires=? WHERE id=?", (newexp, acc_id))
    db.commit()
    add_tx(user["user_id"], "renew", -price, f"Perpanjang {row['vpn_user']} {days}h")
    send(chat_id, f"♻️ <b>{row['vpn_user']}</b> diperpanjang {days} hari.\n📅 Expired baru: {newexp}",
         main_menu(get_user(user["user_id"])))


def do_delete(chat_id, user, acc_id):
    row = db.execute("SELECT * FROM orders WHERE id=? AND user_id=?", (acc_id, user["user_id"])).fetchone()
    if not row:
        return
    try:
        delete_vmess(row["vpn_user"])
    except Exception as e:
        send(chat_id, f"Gagal menghapus: {e}", main_menu(get_user(user["user_id"])))
        return
    db.execute("UPDATE orders SET active=0 WHERE id=?", (acc_id,))
    db.commit()
    add_tx(user["user_id"], "delete", 0, f"Hapus akun {row['vpn_user']}")
    set_quota(row["vpn_user"], None)
    send(chat_id, f"🗑 Akun <b>{row['vpn_user']}</b> sudah dihapus. Saldo tidak dikembalikan.",
         main_menu(get_user(user["user_id"])))


def show_history(chat_id, user, msg_id):
    rows_ = db.execute("SELECT * FROM tx WHERE user_id=? ORDER BY id DESC LIMIT 10",
                       (user["user_id"],)).fetchall()
    if not rows_:
        edit(chat_id, msg_id, "📊 Belum ada transaksi.", kb([back_row()]))
        return
    label = {"order": "🛒 Beli akun", "renew": "♻️ Perpanjang", "topup": "💳 TopUp",
             "trial": "🎁 Trial", "delete": "🗑 Hapus akun", "reseller": "🤝 Reseller",
             "admin": "🛠 Admin"}
    parts = ["📊 <b>Riwayat Transaksi</b>\n"]
    for t in rows_:
        amt = rp(t["amount"]) if t["amount"] else "-"
        if t["amount"] and t["amount"] > 0:
            amt = "+" + amt
        parts.append(f"{t['created_at']} — {label.get(t['type'], t['type'])} {amt}\n  {t['note']}")
    edit(chat_id, msg_id, "\n".join(parts), kb([back_row()]))


def show_reseller(chat_id, user, msg_id):
    if user["status"] == "reseller":
        edit(chat_id, msg_id, "🤝 Status kamu sudah <b>Reseller</b>. Harga khusus otomatis berlaku "
                              "setiap kamu membeli.", kb([back_row()]))
        return
    prices = load_prices()
    disc = prices.get("diskon_reseller_persen", 0)
    rows = [[btn("📩 Ajukan Jadi Reseller", "res:apply")], back_row()]
    edit(chat_id, msg_id,
         f"🤝 <b>Jadi Reseller</b>\nReseller mendapat potongan harga {disc}% untuk semua paket.\n"
         "Klik tombol di bawah untuk mengajukan ke admin.", kb(rows))


def reseller_apply(chat_id, user):
    uname = "@" + user["username"] if user["username"] else user["first_name"]
    rows = [[btn("✅ Setujui Reseller", f"adm:res_ok:{user['user_id']}"),
             btn("❌ Tolak", f"adm:res_no:{user['user_id']}")]]
    for adm in ADMIN_IDS:
        send(adm, f"🤝 <b>Pengajuan reseller</b>\nDari: {uname} (<code>{user['user_id']}</code>)", kb(rows))
    send(chat_id, "📩 Pengajuan terkirim ke admin. Tunggu persetujuan ya.",
         main_menu(get_user(user["user_id"])))


HELP_TEXT = (
    "🆘 <b>Bantuan</b>\n\n"
    "• Buat Akun: pilih durasi & kuota, saldo terpotong, link akun langsung keluar.\n"
    "• TopUp: transfer sesuai info pembayaran, klik 'Saya Sudah Transfer', saldo masuk setelah admin menyetujui.\n"
    "• Akun Saya: lihat sisa kuota & tanggal expired akunmu.\n"
    "• Perpanjang: tambah masa aktif akun sebelum expired.\n"
    "• Hapus Akun: akun dihapus permanen, saldo tidak kembali.\n\n"
    "Masih bingung? Hubungi admin toko."
)


# ---------------------------------------------------------------- admin

def admin_panel(chat_id, msg_id):
    def st(key):
        return "🟢 Buka" if setting(key) == "1" else "🔴 Tutup"
    rows = [
        [btn(f"Buat Akun: {st('order_open')}", "adm:tgl:order_open")],
        [btn(f"TopUp: {st('topup_open')}", "adm:tgl:topup_open")],
        [btn(f"Trial: {st('trial_open')}", "adm:tgl:trial_open")],
        [btn(f"Perpanjang: {st('renew_open')}", "adm:tgl:renew_open")],
        [btn(f"Hapus Akun: {st('delete_open')}", "adm:tgl:delete_open")],
        [btn("💰 Kredit Saldo Manual", "adm:credit")],
        back_row(),
    ]
    pend = db.execute("SELECT COUNT(*) c FROM topups WHERE status='pending'").fetchone()["c"]
    edit(chat_id, msg_id, f"🛠 <b>Panel Admin</b>\nTopup menunggu persetujuan: {pend}\n"
                          "Klik untuk buka/tutup menu:", kb(rows))


def admin_decide_topup(cb_chat, cb_msg, admin, tid, ok):
    row = db.execute("SELECT * FROM topups WHERE id=?", (tid,)).fetchone()
    if not row or row["status"] != "pending":
        return
    if ok:
        db.execute("UPDATE topups SET status='approved' WHERE id=?", (tid,))
        db.execute("UPDATE users SET saldo=saldo+? WHERE user_id=?", (row["amount"], row["user_id"]))
        db.commit()
        add_tx(row["user_id"], "topup", row["amount"], f"TopUp #{tid} disetujui")
        send(row["user_id"], f"💳 TopUp {rp(row['amount'])} <b>disetujui</b>. Saldo kamu bertambah.",
             main_menu(get_user(row["user_id"])))
        verdict = f"✅ TopUp #{tid} ({rp(row['amount'])}) DISUTUJUI oleh admin."
    else:
        db.execute("UPDATE topups SET status='rejected' WHERE id=?", (tid,))
        db.commit()
        send(row["user_id"], f"💳 TopUp {rp(row['amount'])} <b>ditolak</b> admin. "
                             "Pastikan bukti transfermu benar, atau hubungi admin.",
             main_menu(get_user(row["user_id"])))
        verdict = f"❌ TopUp #{tid} ({rp(row['amount'])}) DITOLAK oleh admin."
    edit(cb_chat, cb_msg, verdict)


def admin_decide_reseller(cb_chat, cb_msg, uid_target, ok):
    if ok:
        db.execute("UPDATE users SET status='reseller' WHERE user_id=?", (uid_target,))
        db.commit()
        add_tx(uid_target, "reseller", 0, "Status reseller disetujui")
        send(uid_target, "🤝 Selamat! Pengajuan resellermu <b>disetujui</b>. Harga khusus sudah berlaku.",
             main_menu(get_user(uid_target)))
        verdict = f"✅ Pengguna {uid_target} sekarang Reseller."
    else:
        send(uid_target, "🤝 Pengajuan resellermu belum disetujui admin.",
             main_menu(get_user(uid_target)))
        verdict = f"❌ Pengajuan reseller {uid_target} ditolak."
    edit(cb_chat, cb_msg, verdict)


# ---------------------------------------------------------------- handlers

def handle_message(msg):
    chat_id = msg["chat"]["id"]
    user = ensure_user(msg)
    text = (msg.get("text") or "").strip()

    if text.startswith("/start"):
        states.pop(chat_id, None)
        show_home(chat_id, user)
        return
    if text.startswith("/admin") and user["user_id"] in ADMIN_IDS:
        send(chat_id, "🛠 Panel Admin:", kb([[btn("Buka Panel Admin", "m:admin")]]))
        return

    state = states.pop(chat_id, None)
    if state:
        step, data = state
        if step in ("username_order", "username_trial"):
            username = text.lower()
            if not USER_RE.match(username):
                states[chat_id] = state
                send(chat_id, "Username tidak valid. Aturan: huruf kecil/angka/strip, 3–20 karakter, "
                              "diawali huruf/angka. Kirim ulang:")
                return
            if step == "username_order":
                do_order(chat_id, user, username, data["days"], data["q"], data["price"])
            else:
                do_trial_create(chat_id, user, username)
            return
        if step == "topup_custom":
            digits = re.sub(r"\D", "", text)
            if not digits or not (5000 <= int(digits) <= 2000000):
                states[chat_id] = state
                send(chat_id, "Nominal tidak valid (min Rp5.000, maks Rp2.000.000). Kirim ulang:")
                return
            send(chat_id, "💳 TopUp:", kb([[btn("Lanjut", f"top:amt:{int(digits)}")]]))
            return
        if step == "admin_credit":
            parts = text.split()
            if len(parts) != 2 or not parts[0].isdigit() or not re.fullmatch(r"-?\d+", parts[1]):
                states[chat_id] = state
                send(chat_id, "Format salah. Contoh: <code>7652113800 50000</code>. Kirim ulang:")
                return
            target, amount = int(parts[0]), int(parts[1])
            if not get_user(target):
                send(chat_id, "Pengguna itu belum terdaftar di bot toko.")
                return
            db.execute("UPDATE users SET saldo=saldo+? WHERE user_id=?", (amount, target))
            db.commit()
            add_tx(target, "admin", amount, "Kredit saldo manual oleh admin")
            send(chat_id, f"💰 Saldo {target} diubah {rp(amount)}. Saldo baru: {rp(get_user(target)['saldo'])}")
            send(target, f"💰 Saldomu diubah admin sebesar {rp(amount)}.", main_menu(get_user(target)))
            return

    send(chat_id, "Pilih menu di bawah ya:", main_menu(user))


def handle_callback(cb):
    global _cb_answer
    _cb_answer = ""
    msg = cb["message"]
    chat_id = msg["chat"]["id"]
    msg_id = msg["message_id"]
    user = ensure_user({"from": cb["from"]})
    data = cb.get("data", "")
    parts = data.split(":")

    try:
        if data == "m:home":
            states.pop(chat_id, None)
            show_home(chat_id, user, msg_id)
        elif data == "m:order":
            start_order(chat_id, user, msg_id)
        elif data == "m:trial":
            do_trial(chat_id, user, msg_id)
        elif data == "m:topup":
            start_topup(chat_id, user, msg_id)
        elif data == "m:myacc":
            my_accounts(chat_id, user, msg_id)
        elif data == "m:renew":
            if closed("renew_open"):
                _cb_answer = "Menu Perpanjang sedang ditutup admin."
            else:
                pick_account(chat_id, user, msg_id, "ren")
        elif data == "m:delete":
            if closed("delete_open"):
                _cb_answer = "Menu Hapus Akun sedang ditutup admin."
            else:
                pick_account(chat_id, user, msg_id, "del")
        elif data == "m:history":
            show_history(chat_id, user, msg_id)
        elif data == "m:reseller":
            show_reseller(chat_id, user, msg_id)
        elif data == "m:help":
            edit(chat_id, msg_id, HELP_TEXT, kb([back_row()]))
        elif data == "m:admin" and user["user_id"] in ADMIN_IDS:
            admin_panel(chat_id, msg_id)

        elif parts[0] == "ord" and parts[1] == "dur":
            pick_quota(chat_id, user, msg_id, int(parts[2]), "ord")
        elif parts[0] == "ord" and parts[1] == "q":
            ask_username(chat_id, user, msg_id, "ord", int(parts[2]), parts[3])
        elif parts[0] == "ren" and parts[1] == "acc":
            prices = load_prices()
            acc = db.execute("SELECT * FROM orders WHERE id=?", (int(parts[2]),)).fetchone()
            qlabel = None
            for q, b in prices["kuota"].items():
                if b == acc["quota_bytes"]:
                    qlabel = q
            if qlabel is None:
                qlabel = quota_labels(prices)[0]
            rows = []
            for d in prices["durasi_hari"]:
                price = price_for(prices, user, d, qlabel)
                rows.append([btn(f"📅 +{d} Hari — {rp(price)}", f"ren:go:{acc['id']}:{d}:{price}")])
            rows.append(back_row())
            edit(chat_id, msg_id, f"♻️ Perpanjang <b>{acc['vpn_user']}</b> (exp {acc['expires']})\nPilih durasi:",
                 kb(rows))
        elif parts[0] == "ren" and parts[1] == "go":
            do_renew(chat_id, user, int(parts[2]), int(parts[3]), int(parts[4]))
            show_home(chat_id, get_user(user["user_id"]))
        elif parts[0] == "del" and parts[1] == "acc":
            acc = db.execute("SELECT * FROM orders WHERE id=?", (int(parts[2]),)).fetchone()
            rows = [[btn("🗑 Ya, Hapus Permanen", f"del:go:{acc['id']}")], back_row()]
            edit(chat_id, msg_id,
                 f"🗑 Hapus akun <b>{acc['vpn_user']}</b>?\nAkun terhapus permanen dan saldo tidak kembali.",
                 kb(rows))
        elif parts[0] == "del" and parts[1] == "go":
            do_delete(chat_id, user, int(parts[2]))
            show_home(chat_id, get_user(user["user_id"]))

        elif parts[0] == "top" and parts[1] == "amt":
            topup_invoice(chat_id, user, msg_id, int(parts[2]))
        elif parts[0] == "top" and parts[1] == "custom":
            states[chat_id] = ("topup_custom", {})
            edit(chat_id, msg_id, "✏️ Kirim nominal topup (min Rp5.000):", kb([back_row()]))
        elif parts[0] == "top" and parts[1] == "paid":
            topup_paid(chat_id, user, int(parts[2]))

        elif parts[0] == "res" and parts[1] == "apply":
            reseller_apply(chat_id, user)

        elif parts[0] == "adm" and user["user_id"] in ADMIN_IDS:
            if parts[1] == "tgl":
                key = parts[2]
                set_setting(key, "0" if setting(key) == "1" else "1")
                admin_panel(chat_id, msg_id)
            elif parts[1] in ("topup_ok", "topup_no"):
                admin_decide_topup(chat_id, msg_id, user, int(parts[2]), parts[1] == "topup_ok")
            elif parts[1] in ("res_ok", "res_no"):
                admin_decide_reseller(chat_id, msg_id, int(parts[2]), parts[1] == "res_ok")
            elif parts[1] == "credit":
                states[chat_id] = ("admin_credit", {})
                edit(chat_id, msg_id, "💰 Kirim format: <code>ID nominal</code>\nContoh: <code>7652113800 50000</code> "
                                      "(nominal negatif untuk mengurangi).", kb([back_row()]))
    except Exception:
        traceback.print_exc()
        send(chat_id, "Terjadi kesalahan, coba lagi ya.", main_menu(get_user(user["user_id"])))

    answer_cb(cb["id"], _cb_answer)


def main():
    print(f"Store bot jalan. Admin: {sorted(ADMIN_IDS)}", flush=True)
    offset = None
    while True:
        try:
            params = {"timeout": 30}
            if offset:
                params["offset"] = offset
            res = tg("getUpdates", params)
            for upd in res.get("result", []):
                offset = upd["update_id"] + 1
                try:
                    if "message" in upd:
                        handle_message(upd["message"])
                    elif "callback_query" in upd:
                        handle_callback(upd["callback_query"])
                except Exception:
                    traceback.print_exc()
        except Exception:
            traceback.print_exc()
            time.sleep(3)


if __name__ == "__main__":
    main()
