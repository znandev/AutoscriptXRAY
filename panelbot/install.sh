#!/bin/bash
# Installer Panel Bot Telegram untuk AutoscriptXRAY.
# Jalankan sebagai root dari folder panelbot/ hasil git pull:
#   cd ~/AutoscriptXRAY/panelbot && bash install.sh
set -e
cd "$(dirname "$0")"

if [ "${EUID}" -ne 0 ]; then
    echo "Harus dijalankan sebagai root."
    exit 1
fi

mkdir -p /opt/panelbot /etc/panelbot /var/lib/panelbot

cp bot.py /opt/panelbot/bot.py
chmod +x /opt/panelbot/bot.py

if [ ! -f /etc/panelbot/config.env ]; then
    cat > /etc/panelbot/config.env <<'EOF'
# Token dari @BotFather (isi di VPS ini saja, JANGAN dibagikan / di-commit)
BOT_TOKEN=
# ID Telegram pemilik, pisahkan koma bila lebih dari satu. Cek ID di @userinfobot
ALLOWED_IDS=
EOF
    chmod 600 /etc/panelbot/config.env
    echo "File /etc/panelbot/config.env dibuat (masih kosong)."
fi

cp panelbot.service /etc/systemd/system/panelbot.service
systemctl daemon-reload

echo ""
echo "Install selesai. Langkah berikutnya:"
echo "1. Buat bot di @BotFather (/newbot), ambil tokennya."
echo "2. Isi token + ID Telegram kamu:  nano /etc/panelbot/config.env"
echo "3. Nyalakan bot:                  systemctl enable --now panelbot"
echo "4. Cek status:                    systemctl status panelbot"
echo "   Log:                           journalctl -u panelbot -f"
