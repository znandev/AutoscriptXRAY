#!/bin/bash

# Setup SSH WebSocket + UDPGW - by znandev

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

DEPS_VERSION="deps-v2"
RELEASE_URL="https://github.com/znandev/AutoscriptXRAY/releases/download/${DEPS_VERSION}"

clear

echo -e "${GREEN}▶️ Installing SSH + WebSocket...${NC}"
sleep 1

# ================= VALIDATION =================

if [[ ! -f ~/AutoscriptXRAY/config/issue.net ]]; then
    echo -e "${RED}[ERROR] issue.net not found!${NC}"
    exit 1
fi

# ================= INSTALL DEPENDENCY =================

apt update -y

apt install -y \
    openssh-server \
    stunnel4 \
    curl \
    wget \
    python3 \
    screen \
    git \
    golang-go \
    libtomcrypt1 \
    libtommath1

mkdir -p /usr/local/bin

# ================= INSTALL DROPBEAR =================

echo ""
echo -e "${GREEN}[INFO] Installing Dropbear...${NC}"
echo ""

systemctl stop dropbear 2>/dev/null || true

apt purge -y \
    dropbear \
    dropbear-bin >/dev/null 2>&1 || true

rm -f /usr/sbin/dropbear
rm -f /usr/bin/dbclient
rm -f /usr/bin/dropbearkey

cd /tmp || exit

wget -qO dropbear-bin.deb \
"${RELEASE_URL}/dropbear-bin_2019.78-2build1_amd64.deb" || {
    echo -e "${RED}[ERROR] Failed to download dropbear-bin${NC}"
    exit 1
}

wget -qO dropbear.deb \
"${RELEASE_URL}/dropbear_2019.78-2build1_all.deb" || {
    echo -e "${RED}[ERROR] Failed to download dropbear${NC}"
    exit 1
}

dpkg -i dropbear-bin.deb dropbear.deb

DROPBEAR_VER=$(dropbear -V 2>&1)

echo "$DROPBEAR_VER" | grep -q "2019.78" || {
    echo -e "${RED}[ERROR] Wrong Dropbear installed!${NC}"
    exit 1
}

# ================= HOSTKEY =================

mkdir -p /etc/dropbear

[ ! -f /etc/dropbear/dropbear_rsa_host_key ] && \
dropbearkey -t rsa -f /etc/dropbear/dropbear_rsa_host_key

[ ! -f /etc/dropbear/dropbear_ecdsa_host_key ] && \
dropbearkey -t ecdsa -f /etc/dropbear/dropbear_ecdsa_host_key

# ================= BANNER =================

cp ~/AutoscriptXRAY/config/issue.net /etc/issue.net
chmod 644 /etc/issue.net

# ================= DROPBEAR CONFIG =================

cat > /etc/default/dropbear <<EOF
NO_START=0
DROPBEAR_PORT=109
DROPBEAR_EXTRA_ARGS="-p 143 -W 65536 -b /etc/issue.net"
DROPBEAR_RECEIVE_WINDOW=65536
EOF

# ================= DROPBEAR SERVICE =================

cat > /etc/systemd/system/dropbear.service <<EOF
[Unit]
Description=Dropbear SSH Server
After=network.target

[Service]
ExecStart=/usr/sbin/dropbear -E -F -p 109 -p 143 -W 65536 -b /etc/issue.net
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# ================= BUILD GO WS =================

echo ""
echo -e "${GREEN}[INFO] Building Go WebSocket Services...${NC}"
echo ""

if ! command -v go >/dev/null 2>&1; then
    apt install -y golang-go
fi

cd ~/AutoscriptXRAY/internal/go || exit 1

go build -ldflags="-s -w" \
    -o /usr/local/bin/dropbearws \
    ./dropbear-ws || {
    echo -e "${RED}[ERROR] Failed to build sshws${NC}"
    exit 1
}

go build -ldflags="-s -w" \
    -o /usr/local/bin/stunnelws \
    ./stunnel-ws || {
    echo -e "${RED}[ERROR] Failed to build stunnelws${NC}"
    exit 1
}

chmod +x /usr/local/bin/dropbearws
chmod +x /usr/local/bin/stunnelws

cp ~/AutoscriptXRAY/internal/go/dropbear-ws.service \
    /etc/systemd/system/dropbear-ws.service

cp ~/AutoscriptXRAY/internal/go/stunnel-ws.service \
    /etc/systemd/system/stunnel-ws.service


# ================= INSTALL BADVPN UDPGW =================

echo ""
echo -e "${GREEN}[INFO] Installing BadVPN UDPGW...${NC}"
echo ""

wget -qO /usr/local/bin/badvpn-udpgw \
"${RELEASE_URL}/badvpn-udpgw" || {
    echo -e "${RED}[ERROR] Failed to download BadVPN UDPGW${NC}"
    exit 1
}

chmod +x /usr/local/bin/badvpn-udpgw

# ================= UDPGW SERVICE =================

cp ~/AutoscriptXRAY/sshws/udpgw.service \
/etc/systemd/system/

# ================= INSTALL UDP CUSTOM =================

echo ""
echo -e "${GREEN}[INFO] Installing UDP Custom...${NC}"
echo ""

wget -qO /usr/local/bin/udp-custom \
"${RELEASE_URL}/udp-custom-linux-amd64" || {
    echo -e "${RED}[ERROR] Failed to download UDP Custom${NC}"
    exit 1
}

chmod +x /usr/local/bin/udp-custom

mkdir -p /etc/udp-custom

cp ~/AutoscriptXRAY/config/udp-custom.json \
/etc/udp-custom/config.json

# ================= UDP CUSTOM SERVICE =================

cp ~/AutoscriptXRAY/sshws/udp-custom.service \
/etc/systemd/system/

# ================= PERMISSION =================

chmod 644 /etc/systemd/system/dropbear.service
chmod 644 /etc/systemd/system/dropbear-ws.service
chmod 644 /etc/systemd/system/stunnel-ws.service
chmod 644 /etc/systemd/system/udpgw.service
chmod 644 /etc/systemd/system/udp-custom.service

# ================= RELOAD =================

systemctl daemon-reload
systemctl daemon-reexec

# ================= ENABLE SERVICES =================

systemctl enable ssh
systemctl restart ssh

systemctl enable dropbear
systemctl restart dropbear

systemctl enable dropbear-ws
systemctl restart dropbear-ws

systemctl enable stunnel-ws
systemctl restart stunnel-ws

systemctl enable udpgw
systemctl restart udpgw

systemctl enable udp-custom
systemctl restart udp-custom

# ================= RECHECK SERVICES ==============

sleep 2

for svc in \
    ssh \
    dropbear \
    ws-dropbear \
    ws-stunnel \
    udpgw \
    udp-custom
do
    systemctl is-active --quiet "$svc" || {
        echo -e "${RED}[ERROR] Service $svc failed!${NC}"
        exit 1
    }
done

# ================= NOLOGIN WS ====================

cat > /etc/profile.d/no-login.sh <<'EOF'
#!/bin/bash

[[ "$USER" == "root" ]] && return

clear
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " SSH WS ACCOUNT ONLY"
echo " SHELL ACCESS DENIED"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

sleep 2

pkill -9 -u "$USER"
EOF

chmod +x /etc/profile.d/no-login.sh

# ================= HOLD DROPBEAR =================

apt-mark hold dropbear dropbear-bin >/dev/null 2>&1 || true

# ================= INSTALL LOG =================

cat >> /root/log-install.txt <<EOF

━━━━━━━━━━━━━━━━━━━━━━
SSH PANEL
━━━━━━━━━━━━━━━━━━━━━━

OpenSSH             : 22
Dropbear            : 109,143
SSH Websocket       : 2082
SSH SSL Websocket   : 2096
BadVPN UDPGW        : 7300
Port UdpSSH         : 1-65535

━━━━━━━━━━━━━━━━━━━━━━

EOF

# ================= DONE =================

clear

echo ""
echo -e "${GREEN}[ OK ] SSH + WS + UDPGW Installed${NC}"
echo ""

ss -tulnp | grep -E '22|109|143|2082|2096|7300|36712'

echo ""
echo -e "${GREEN}[INFO] Service Status:${NC}"

systemctl --no-pager --type=service | \
grep -E 'dropbear|ssh|ws|udpgw|udp|dropbear-ws|stunnel-ws'

echo ""
dropbear -V
echo ""
