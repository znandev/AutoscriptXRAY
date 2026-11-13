#!/bin/bash
# Hapus SlowDNS (DNSTT) — mengembalikan kondisi sebelum install.
#   bash slowdns/uninstall-slowdns.sh
# Menghapus: service dnstt, binary, kunci di /etc/slowdns,
# dan drop-in resolved. Install ulang = kunci baru =
# client harus update public key.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Jalankan sebagai root (sudo)." >&2
  exit 1
fi

systemctl disable --now dnstt 2>/dev/null || true
rm -f /etc/systemd/system/dnstt.service
systemctl daemon-reload
rm -f /usr/local/bin/dnstt-server
rm -rf /etc/slowdns
rm -f /etc/systemd/resolved.conf.d/slowdns.conf
systemctl restart systemd-resolved 2>/dev/null || true

echo "SlowDNS sudah dihapus."
