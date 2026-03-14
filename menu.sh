#!/bin/bash
# Main Menu

# Warna
YELLOW='\e[1;33m'
CYAN='\e[1;36m'
GREEN='\e[1;32m'
RED='\e[1;31m'
NC='\e[0m'

CONFIG="/etc/xray/config.json"
LOG="/var/log/xray/access.log"

# SYSTEM INFO
IP=$(hostname -I | awk '{print $1}')
ISP=$(curl -s ipinfo.io/org | cut -d " " -f2-)

UPTIME=$(uptime -p | sed 's/up //')
SERVER_TIME=$(date "+%d-%m-%Y %H:%M:%S")

CPU_MODEL=$(lscpu | grep "Model name" | head -1 | sed 's/Model name:[ \t]*//')
CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | awk '{print $2+$4}')

RAM=$(free -m | awk 'NR==2{printf "%s / %s MB", $3,$2 }')
DISK=$(df -h / | awk 'NR==2 {print $3 " / " $2}')

KERNEL=$(uname -r)
XRAY_VERSION=$(xray version | head -1 | awk '{print $2}')

# NETWORK TRAFFIC
RX=$(cat /proc/net/dev | awk '/eth0/ {print $2}')
TX=$(cat /proc/net/dev | awk '/eth0/ {print $10}')

RX_MB=$((RX / 1024 / 1024))
TX_MB=$((TX / 1024 / 1024))

# XRAY STATUS
STATUS=$(systemctl is-active xray)

if [[ $STATUS == "active" ]]; then
STATUS="${GREEN}🟢 ACTIVE${NC}"
else
STATUS="${RED}🔴 NOT RUNNING${NC}"
fi

# USER COUNT
VMESS=$(jq '[.inbounds[] | select(.tag=="vmess-tls").settings.clients[]] | length' $CONFIG)
VLESS=$(jq '[.inbounds[] | select(.tag=="vless-tls").settings.clients[]] | length' $CONFIG)
TROJAN=$(jq '[.inbounds[] | select(.tag=="trojan-tls").settings.clients[]] | length' $CONFIG)

TOTAL=$((VMESS + VLESS + TROJAN))

# ONLINE USERS
ONLINE=$(grep "accepted" $LOG 2>/dev/null | awk -F'from ' '{print $2}' | cut -d':' -f1 | sort -u | wc -l)

clear

echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}              ⚡ ZNANDEV XRAY PANEL ⚡${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e " 🖥️  System Information"
echo -e " ─────────────────────────────────────────────"

printf " 🌐 %-12s : %s\n" "IP Address" "$IP"
printf " 🏢 %-12s : %s\n" "ISP" "$ISP"
printf " ⏰ %-12s : %s\n" "Server Time" "$SERVER_TIME"
printf " ⏳ %-12s : %s\n" "Uptime" "$UPTIME"
printf " 🧠 %-12s : %s\n" "CPU Model" "$CPU_MODEL"
printf " ⚙️  %-12s : %s %%\n" "CPU Usage" "$CPU_USAGE"
printf " 💾 %-12s : %s\n" "RAM Usage" "$RAM"
printf " 🗄️  %-12s : %s\n" "Storage" "$DISK"

echo ""
echo -e " 🔧 System Software"
echo -e " ─────────────────────────────────────────────"

printf " 🐧 %-12s : %s\n" "Kernel" "$KERNEL"
printf " 🚀 %-12s : %s\n" "XRAY Version" "$XRAY_VERSION"

echo ""
echo -e " 📡 Network Traffic"
echo -e " ─────────────────────────────────────────────"

printf " ⬇️  %-12s : %s MB\n" "Download" "$RX_MB"
printf " ⬆️  %-12s : %s MB\n" "Upload" "$TX_MB"

echo ""
echo -e " 👥 User Statistics"
echo -e " ─────────────────────────────────────────────"

printf " 👤 %-12s : %b\n" "Total Users" "$TOTAL"
printf " 🔐 %-12s : %b\n" "VMESS Users" "$VMESS"
printf " 🧬 %-12s : %b\n" "VLESS Users" "$VLESS"
printf " 🛡️  %-12s : %b\n" "TROJAN Users" "$TROJAN"

echo ""
echo -e " 🚀 XRAY Status : $STATUS"

echo ""
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}                ⛓️ MENU UTAMA ⛓️${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e " [1] 🚀 Menu Vmess"
echo -e " [2] 🧬 Menu Vless"
echo -e " [3] 🛡️  Menu Trojan"
echo -e " [4] 🔒 Menu Shadowsocks"
echo -e " [5] 🌐 Menu WireGuard"
echo -e " [6] 🧰 Menu Tools"
echo -e " [7] 📊 Status Service"
echo -e " [8] 🧹 Clear RAM Cache"
echo -e " [9] 🔄 Reboot VPS"
echo -e " [x] ❌ Exit"

echo ""
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

read -p "👉 Pilih menu: " menu
echo ""

case $menu in
  1) m-vmess ;;
  2) m-vless ;;
  3) m-trojan ;;
  4) m-ssws ;;
  5) m-wg ;;
  6) tools-menu ;;
  7) running ;;
  8) clearcache ;;
  9) reboot ;;
  x) exit ;;
  *) echo "❌ Pilihan tidak valid!" ; sleep 1 ; menu ;;
esac
