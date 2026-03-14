#!/bin/bash

clear

BLUE='\033[0;34m'
GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "\E[44;1;39m            DELETE VMESS ACCOUNT             \E[0m"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${CYAN}📋 List User VMess:${NC}"
echo ""

CONFIG="/etc/xray/config.json"

users=$(jq -r '.inbounds[] | select(.tag=="vmess-tls") | .settings.clients[].email' $CONFIG)

if [[ -z "$users" ]]; then
echo -e "${RED}Tidak ada user VMess!${NC}"
read -n 1 -s -r -p "Tekan apa saja untuk kembali..."
m-vmess
exit
fi

num=1
for user in $users
do
printf "${GREEN}[%s]${NC} %s\n" "$num" "$user"
((num++))
done

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
read -rp "👉 Masukkan username yang ingin dihapus: " user
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

jq --arg user "$user" '
(.inbounds[] | select(.tag=="vmess-tls").settings.clients) |=
map(select(.email != $user)) |
(.inbounds[] | select(.tag=="vmess-nontls").settings.clients) |=
map(select(.email != $user))
' $CONFIG > /tmp/config.json

mv /tmp/config.json $CONFIG

systemctl restart xray

echo ""
echo -e "${GREEN}✅ User VMess '${user}' berhasil dihapus!${NC}"
echo ""

read -n 1 -s -r -p "Tekan apa saja untuk kembali ke menu..."

m-vmess
