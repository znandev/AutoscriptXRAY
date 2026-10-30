# -*- coding: utf-8 -*-
"""
Penyimpanan state kuota panelbot (dipakai bersama oleh bot.py dan quota-check.py).

File state: /var/lib/panelbot/quota-state.json
Format per user:
  {
    "quota":    <bytes atau null bila unlimited>,
    "used":     <bytes terpakai (akumulasi delta antar-cek)>,
    "last_up":  <counter uplink terakhir dari API Xray>,
    "last_down":<counter downlink terakhir dari API Xray>,
    "disabled": <true bila sudah dinonaktifkan karena kuota habis>
  }

Semua tulis dilakukan di bawah flock + tulis atomik (tmp + rename),
jadi bot dan checker berkala tidak saling merusak file.
"""

import fcntl
import json
import os
import tempfile

STATE_PATH = "/var/lib/panelbot/quota-state.json"
LOCK_PATH = "/var/lib/panelbot/quota-state.lock"
GB = 1024 ** 3


def _load_unlocked():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save_unlocked(data):
    d = os.path.dirname(STATE_PATH)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".quota-state-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, sort_keys=True)
        os.replace(tmp, STATE_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def update(fn):
    """Jalankan fn(data)->result di bawah lock, simpan hasilnya. Return result."""
    os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
    with open(LOCK_PATH, "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            data = _load_unlocked()
            result = fn(data)
            _save_unlocked(data)
            return result
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def snapshot():
    """Baca state tanpa mengubah (tetap di bawah lock bersama)."""
    os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
    with open(LOCK_PATH, "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        try:
            return _load_unlocked()
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def set_quota(username, quota_bytes):
    """Daftarkan akun baru dengan kuota (None = unlimited)."""
    def _do(data):
        data[username] = {
            "quota": quota_bytes,
            "used": 0,
            "last_up": 0,
            "last_down": 0,
            "disabled": False,
        }
    update(_do)


def fmt_bytes(n):
    if n is None:
        return "∞"
    if n >= 1024 ** 4:
        return f"{n / (1024 ** 4):.2f} TB"
    if n >= GB:
        return f"{n / GB:.1f} GB"
    if n >= 1024 ** 2:
        return f"{n / (1024 ** 2):.1f} MB"
    return f"{n} B"
