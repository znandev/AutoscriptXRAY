#!/bin/bash
# Installer bot toko VPN (storebot) untuk AutoscriptXRAY.
# Jalankan sebagai root dari folder storebot/ di repo.
set -e
cd "$(dirname "$0")"

install -d /opt/storebot /etc/storebot /var/lib/storebot
install -m 0644 storebot.py /opt/storebot/storebot.py
install -m 0644 storebot.service /etc/systemd/system/storebot.service

if [ -f qris.png.b64 ]; then
    base64 -d qris.png.b64 > /etc/storebot/qris.png
    echo "Gambar QRIS terpasang ke /etc/storebot/qris.png."
elif [ -f qris.png ]; then
    install -m 0644 qris.png /etc/storebot/qris.png
    echo "Gambar QRIS terpasang ke /etc/storebot/qris.png."
fi

if [ ! -f /etc/storebot/config.env ]; then
    cat > /etc/storebot/config.env <<'EOF'
BOT_TOKEN=
ADMIN_IDS=7652113800
SHOP_NAME=Nexus Vpn
PAYMENT_INFO=QRIS: (isi nomor/nama QRIS kamu)\nDANA: (isi nomor)\nOVO: (isi nomor)
EOF
    chmod 600 /etc/storebot/config.env
    echo "File /etc/storebot/config.env dibuat - isi BOT_TOKEN bot toko dari @BotFather."
fi

if [ ! -f /etc/storebot/prices.json ]; then
    install -m 0644 prices.json /etc/storebot/prices.json
    echo "File /etc/storebot/prices.json dibuat dari harga bawaan (sementara)."
fi

systemctl daemon-reload
echo ""
echo "Install selesai. Langkah berikutnya:"
echo "1. Buat bot TOKO baru di @BotFather (/newbot) - terpisah dari bot panel admin."
echo "2. Isi config:  nano /etc/storebot/config.env"
echo "   (BOT_TOKEN, ADMIN_IDS, SHOP_NAME, PAYMENT_INFO = info transfer untuk topup manual)"
echo "3. Sesuaikan harga:  nano /etc/storebot/prices.json"
echo "4. Nyalakan bot:     systemctl enable --now storebot"
echo "   Cek status:       systemctl status storebot"
echo "   Log bot:          journalctl -u storebot -f"
echo ""
echo "Catatan: statistik kuota harus aktif (panelbot: bash enable-stats.sh)"
echo "agar pemakaian kuota tampil di menu Akun Saya."
