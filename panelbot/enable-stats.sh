#!/bin/bash
# Aktifkan statistik trafik per user di Xray (sekali jalan).
#
# Kuota per akun panelbot membaca counter trafik lewat API Xray
# (StatsService). Script ini menambal /etc/xray/config.json:
#   - blok "stats" + "api" (StatsService)
#   - policy levels 0: statsUserUplink/Downlink = true
#   - inbound "api" (dokodemo-door, 127.0.0.1:10085) + routing rule-nya
#
# Aman dijalankan ulang (idempotent): bila sudah aktif, tidak mengubah apa pun.
# Backup selalu dibuat di /etc/xray/config.json.pre-stats sebelum menambal;
# config divalidasi `xray -test` dan dikembalikan bila validasi gagal.
set -e

CONFIG=/etc/xray/config.json
BACKUP=/etc/xray/config.json.pre-stats

if [ "${EUID}" -ne 0 ]; then
    echo "Harus dijalankan sebagai root."
    exit 1
fi
if [ ! -f "$CONFIG" ]; then
    echo "Config Xray tidak ditemukan di $CONFIG"
    exit 1
fi

XRAY_BIN="$(command -v xray || true)"
[ -z "$XRAY_BIN" ] && [ -x /usr/local/bin/xray ] && XRAY_BIN=/usr/local/bin/xray
if [ -z "$XRAY_BIN" ]; then
    echo "Binary xray tidak ditemukan."
    exit 1
fi

if jq -e '.api.services | index("StatsService")' "$CONFIG" >/dev/null 2>&1 \
   && jq -e '[.inbounds[] | select(.tag=="api")] | length > 0' "$CONFIG" >/dev/null 2>&1; then
    echo "Statistik per user SUDAH aktif. Tidak ada perubahan."
    exit 0
fi

cp "$CONFIG" "$BACKUP"
echo "Backup dibuat: $BACKUP"

tmp="$(mktemp)"
jq '
  .stats = (.stats // {})
  | .api = {"tag": "api", "services": ["StatsService"]}
  | .policy = (.policy // {})
  | .policy.levels = ((.policy.levels // {}) + {"0": (((.policy.levels // {})["0"] // {}) + {"statsUserUplink": true, "statsUserDownlink": true})})
  | .policy.system = ((.policy.system // {}) + {"statsInboundUplink": true, "statsInboundDownlink": true})
  | .inbounds = (.inbounds + (if [.inbounds[] | select(.tag=="api")] | length == 0
      then [{"tag": "api", "listen": "127.0.0.1", "port": 10085, "protocol": "dokodemo-door",
              "settings": {"address": "127.0.0.1"}}]
      else [] end))
  | .routing = (.routing // {"domainStrategy": "AsIs", "rules": []})
  | .routing.rules = ((.routing.rules // []) + (if [.routing.rules[]? | select(.outboundTag=="api")] | length == 0
      then [{"type": "field", "inboundTag": ["api"], "outboundTag": "api"}]
      else [] end))
' "$CONFIG" > "$tmp"

if ! "$XRAY_BIN" -test -config "$tmp" >/dev/null 2>&1; then
    echo "Validasi config GAGAL. Config asli tidak diubah."
    rm -f "$tmp"
    exit 1
fi

mv "$tmp" "$CONFIG"
systemctl restart xray
sleep 2
if systemctl is-active --quiet xray; then
    echo "Statistik per user AKTIF. Xray jalan normal dengan config baru."
    echo "Counter mulai menghitung dari 0 sejak restart ini."
else
    echo "Xray gagal start dengan config baru — mengembalikan backup..."
    cp "$BACKUP" "$CONFIG"
    systemctl restart xray
    echo "Config lama dikembalikan. Kuota belum bisa aktif; kirim log ke pengelola."
    exit 1
fi
