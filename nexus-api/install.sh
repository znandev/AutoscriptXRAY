#!/bin/bash
# Installer Nexus API (API order akun VPN milik sendiri).
# Jalankan sebagai root dari folder nexus-api/ hasil git pull:
#   cd ~/AutoscriptXRAY/nexus-api && bash install.sh
# Aman dijalankan ulang untuk update: config & token TIDAK ditimpa.
set -e
cd "$(dirname "$0")"

if [ "${EUID}" -ne 0 ]; then
    echo "Harus dijalankan sebagai root."
    exit 1
fi

mkdir -p /opt/nexus-api /etc/nexus-api /var/lib/nexus-api

cp api.py /opt/nexus-api/
chmod +x /opt/nexus-api/api.py

if [ ! -f /etc/nexus-api/config.env ]; then
    TOKEN=$(openssl rand -hex 24)
    cat > /etc/nexus-api/config.env <<EOF
# Token rahasia API (otomatis dibuat installer; JANGAN dibagikan/di-commit)
API_TOKEN=${TOKEN}
# Hanya localhost: bot pemesan harus jalan di VPS yang sama.
BIND_HOST=127.0.0.1
BIND_PORT=8788
SERVER_ID=nexus-1
EOF
    chmod 600 /etc/nexus-api/config.env
    echo "File /etc/nexus-api/config.env dibuat (token acak sudah terisi)."
fi

cp nexus-api.service /etc/systemd/system/
systemctl daemon-reload

echo ""
echo "Install selesai. Langkah berikutnya:"
echo "1. Nyalakan API:    systemctl enable --now nexus-api"
echo "2. Cek status:      systemctl status nexus-api"
echo "3. Lihat token ay:  grep API_TOKEN /etc/nexus-api/config.env"
echo "4. Tes dari VPS:    curl -s -H \"Authorization: Bearer <token>\" http://127.0.0.1:8788/api/v1/health"
