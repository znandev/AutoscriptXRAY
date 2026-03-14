#!/bin/bash

clear

BLUE='\033[0;34m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

CONFIG="/etc/xray/config.json"

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "\E[44;1;39m            PERPANJANG AKUN VLESS            \E[0m"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${CYAN}📋 Daftar User VLESS:${NC}"
echo ""

users=$(jq -r '.inbounds[] | select(.tag=="vless-tls") | .settings.clients[].email' $CONFIG)

for user in $users
do
echo -e " - ${GREEN}$user${NC}"
done

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

read -rp "Masukkan username yang ingin diperpanjang: " user

if ! echo "$users" | grep -w "$user" >/dev/null; then
echo -e "${RED}User tidak ditemukan!${NC}"
sleep 2
m-vless
exit
fi

read -rp "Tambahkan masa aktif (hari): " masaaktif

exp=$(date -d "$masaaktif days" +"%Y-%m-%d")

systemctl restart xray

clear
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "\E[44;1;39m            AKUN BERHASIL DIPERPANJANG       \E[0m"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "User      : ${GREEN}$user${NC}"
echo -e "Expired   : ${GREEN}$exp${NC}"
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

read -n 1 -s -r -p "Tekan apa saja untuk kembali..."

m-vless
