#!/bin/bash

clear
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "       Add VMess User"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━"

read -rp "Username : " user
read -rp "Expired (days): " masaaktif

uuid=$(cat /proc/sys/kernel/random/uuid)
exp=$(date -d "$masaaktif days" +"%Y-%m-%d")

domain=$(cat /etc/xray/domain)

CONFIG="/etc/xray/config.json"

# tambah user ke vmess TLS
jq --arg uuid "$uuid" --arg user "$user" '
(.inbounds[] | select(.tag=="vmess-tls").settings.clients) += 
[{"id":$uuid,"alterId":0,"email":$user}]
' $CONFIG > /tmp/config.json

mv /tmp/config.json $CONFIG

# tambah user ke vmess non TLS
jq --arg uuid "$uuid" --arg user "$user" '
(.inbounds[] | select(.tag=="vmess-nontls").settings.clients) += 
[{"id":$uuid,"alterId":0,"email":$user}]
' $CONFIG > /tmp/config.json

mv /tmp/config.json $CONFIG

systemctl restart xray

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " XRAY VMESS ACCOUNT"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "User   : $user"
echo "Domain : $domain"
echo "UUID   : $uuid"
echo "Exp    : $exp"

vmesslink="vmess://$(echo -n "{\"v\":\"2\",\"ps\":\"${user}\",\"add\":\"${domain}\",\"port\":\"443\",\"id\":\"${uuid}\",\"aid\":\"0\",\"net\":\"ws\",\"path\":\"/vmess\",\"type\":\"none\",\"host\":\"${domain}\",\"tls\":\"tls\"}" | base64 -w 0)"

echo ""
echo "VMESS LINK"
echo "$vmesslink"
echo ""

m-vmess
