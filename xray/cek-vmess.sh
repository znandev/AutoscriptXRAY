#!/bin/bash

clear

BLUE='\033[0;34m'
GREEN='\033[0;32m'
NC='\033[0m'

LOG="/var/log/xray/access.log"
CONFIG="/etc/xray/config.json"

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "\E[44;1;39m            CEK LOGIN VMESS USER             \E[0m"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

printf "%-15s %-18s\n" "USERNAME" "IP CLIENT"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

users=$(jq -r '.inbounds[] | select(.tag=="vmess-tls") | .settings.clients[].email' $CONFIG)

ips=$(grep "accepted" $LOG \
| awk -F'from ' '{print $2}' \
| cut -d':' -f1 \
| grep -Eo '([0-9]{1,3}\.){3}[0-9]{1,3}' \
| grep -v "127.0.0.1" \
| sort -u)

for user in $users
do
for ip in $ips
do
printf "${GREEN}%-15s${NC} %-18s\n" "$user" "$ip"
done
done

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

read -n 1 -s -r -p "Tekan apa saja untuk kembali ke menu..."

m-vmess
