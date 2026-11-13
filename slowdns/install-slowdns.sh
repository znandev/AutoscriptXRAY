#!/bin/bash
# SlowDNS (DNSTT) add-on untuk AutoscriptXRAY — VPS UpCloud baru
# Domain : slowaethernal.eu.cc
# NS zone: slow.slowaethernal.eu.cc  (di-delegasikan ke dns.slowaethernal.eu.cc)
#
# Cara pakai (sebagai root):
#   bash slowdns/install-slowdns.sh [nameserver]
#   nameserver default: slow.slowaethernal.eu.cc
#
# Yang dilakukan script ini:
#   1. Install git + Go, lalu build dnstt-server dari source upstream
#      (proyek DNSTT, public domain — https://www.bamsoftware.com/software/dnstt/)
#   2. Generate keypair di /etc/slowdns (privat key TIDAK pernah keluar dari VPS)
#   3. Jalankan dnstt-server di UDP 53 sebagai service systemd,
#      meneruskan tunnel ke SSH 127.0.0.1:22
#   4. Cetak Nameserver + Public key (dibutuhkan aplikasi SlowDNS di client)
#      dan simpan di /etc/slowdns/info.txt
#
# Prasyarat DNS (di Cloudflare, zone slowaethernal.eu.cc — keduanya DNS-only):
#   A  dns  -> 213.163.201.138
#   NS slow -> dns.slowaethernal.eu.cc
set -euo pipefail

NS="${1:-slow.slowaethernal.eu.cc}"
KEY_DIR="/etc/slowdns"
UPSTREAM="https://www.bamsoftware.com/git/dnstt.git"

if [ "$(id -u)" -ne 0 ]; then
  echo "Jalankan sebagai root (sudo)." >&2
  exit 1
fi

echo "== SlowDNS install =="
echo "Nameserver zone : $NS"
echo "Forward target  : 127.0.0.1:22 (SSH)"
echo ""

# 1. Paket dasar
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y git golang curl iproute2

# 2. Pastikan UDP 53 bebas.
#    Kalau yang memegang hanya stub listener systemd-resolved
#    (127.0.0.53 / 127.0.0.54 — ss menampilkannya sebagai 127.0.0.53%lo:53),
#    matikan lewat drop-in (reversibel: hapus file drop-in + restart resolved).
#    Kalau ada pemakai lain, berhenti dengan error.
if ss -ulnp 2>/dev/null | grep -q ':53[[:space:]]'; then
  echo "Port UDP 53 sedang dipakai:"
  ss -ulnp 2>/dev/null | grep ':53[[:space:]]' || true
  if ss -ulnp 2>/dev/null | grep ':53[[:space:]]' | grep -qv 'systemd-resolve'; then
    echo "ERROR: UDP 53 dipakai sesuatu selain systemd-resolved. Bebaskan dulu port 53." >&2
    exit 1
  fi
  echo "Itu stub listener systemd-resolved — dimatikan lewat drop-in."
  mkdir -p /etc/systemd/resolved.conf.d
  printf '[Resolve]\nDNS=8.8.8.8\nDNSStubListener=no\n' \
    > /etc/systemd/resolved.conf.d/slowdns.conf
  ln -sf /run/systemd/resolve/resolv.conf /etc/resolv.conf
  systemctl restart systemd-resolved
  sleep 2
fi
if ss -ulnp 2>/dev/null | grep -q ':53[[:space:]]'; then
  echo "ERROR: UDP 53 masih dipakai sesuatu yang lain. Bebaskan dulu port 53." >&2
  ss -ulnp 2>/dev/null | grep ':53[[:space:]]' || true
  exit 1
fi

# 3. Build dnstt-server dari source upstream
rm -rf /tmp/dnstt-build
git clone "$UPSTREAM" /tmp/dnstt-build
cd /tmp/dnstt-build/dnstt-server
go build -o /usr/local/bin/dnstt-server .
cd /
rm -rf /tmp/dnstt-build
chmod +x /usr/local/bin/dnstt-server

# 4. Keypair (dibuat di VPS ini saja)
mkdir -p "$KEY_DIR"
chmod 700 "$KEY_DIR"
if [ ! -f "$KEY_DIR/server.key" ] || [ ! -f "$KEY_DIR/server.pub" ]; then
  /usr/local/bin/dnstt-server -gen-key \
    -privkey-file "$KEY_DIR/server.key" \
    -pubkey-file "$KEY_DIR/server.pub"
  chmod 600 "$KEY_DIR/server.key"
  chmod 644 "$KEY_DIR/server.pub"
else
  echo "Kunci sudah ada — dipakai ulang (tidak dibuat baru)."
fi

# 5. Pastikan SSH mengizinkan TCP forwarding (dibutuhkan tunnel dnstt).
#    Restart sshd tidak memutus sesi SSH yang sedang berjalan.
if [ -f /etc/ssh/sshd_config ]; then
  if grep -qE '^[[:space:]]*AllowTcpForwarding[[:space:]]+no' /etc/ssh/sshd_config; then
    sed -i -E 's/^[[:space:]]*AllowTcpForwarding[[:space:]]+no/AllowTcpForwarding yes/' \
      /etc/ssh/sshd_config
    systemctl restart ssh || systemctl restart sshd || true
  elif ! grep -qE '^[[:space:]]*AllowTcpForwarding[[:space:]]+yes' /etc/ssh/sshd_config; then
    echo 'AllowTcpForwarding yes' >> /etc/ssh/sshd_config
    systemctl restart ssh || systemctl restart sshd || true
  fi
fi

# 6. Systemd unit
cat > /etc/systemd/system/dnstt.service <<EOF
[Unit]
Description=DNSTT SlowDNS server ($NS -> 127.0.0.1:22)
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/dnstt-server -udp :53 -privkey-file $KEY_DIR/server.key $NS 127.0.0.1:22
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now dnstt
sleep 2
if ! systemctl is-active --quiet dnstt; then
  echo "ERROR: service dnstt tidak jalan." >&2
  journalctl -u dnstt -n 30 --no-pager || true
  exit 1
fi

# 7. Ringkasan untuk client
PUBKEY="$(cat "$KEY_DIR/server.pub")"
cat > /etc/slowdns/info.txt <<EOF
SlowDNS (DNSTT) — slowaethernal.eu.cc
Nameserver : $NS
Public key : $PUBKEY
Forward    : 127.0.0.1:22 (SSH)
Service    : dnstt (systemctl status dnstt)
Catatan    : buat akun SSH lewat menu ([1] SSH), lalu pakai di aplikasi
             SlowDNS dengan nameserver + public key di atas.
EOF

echo ""
echo "====================== SLOWDNS AKTIF ======================"
echo "Nameserver : $NS"
echo "Public key : $PUBKEY"
echo "Service    : $(systemctl is-active dnstt)"
echo "Info tersimpan di /etc/slowdns/info.txt"
echo "==========================================================="
echo "Jangan lupa 2 record di Cloudflare (DNS-only):"
echo "  A  dns  -> 213.163.201.138"
echo "  NS slow -> dns.slowaethernal.eu.cc"
