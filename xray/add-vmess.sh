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

clear
echo -e "\033[0;34m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m" | tee -a /etc/log-create-vmess.log
echo -e "\E[44;1;39m        XRAY VMess ACCOUNT        \E[0m" | tee -a /etc/log-create-vmess.log
echo -e "\033[0;34m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m" | tee -a /etc/log-create-vmess.log
echo -e "Remarks        : ${user}" | tee -a /etc/log-create-vmess.log
echo -e "Domain         : ${domain}" | tee -a /etc/log-create-vmess.log
echo -e "Wildcard       : (bug.com).${domain}" | tee -a /etc/log-create-vmess.log
echo -e "Port TLS       : ${tls}" | tee -a /etc/log-create-vmess.log
echo -e "Port none TLS  : ${none}" | tee -a /etc/log-create-vmess.log
echo -e "Port gRPC      : ${tls}" | tee -a /etc/log-create-vmess.log
echo -e "id             : ${uuid}" | tee -a /etc/log-create-vmess.log
echo -e "Alter ID       : 0" | tee -a /etc/log-create-vmess.log
echo -e "Encryption     : auto" | tee -a /etc/log-create-vmess.log
echo -e "Network        : ws / grpc" | tee -a /etc/log-create-vmess.log
echo -e "Path           : /vmess" | tee -a /etc/log-create-vmess.log
echo -e "ServiceName    : vmess-grpc" | tee -a /etc/log-create-vmess.log
echo -e "\033[0;34m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m" | tee -a /etc/log-create-vmess.log
echo -e "Link TLS       : ${vmesslink1}" | tee -a /etc/log-create-vmess.log
echo -e "\033[0;34m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m" | tee -a /etc/log-create-vmess.log
echo -e "Link none TLS  : ${vmesslink2}" | tee -a /etc/log-create-vmess.log
echo -e "\033[0;34m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m" | tee -a /etc/log-create-vmess.log
echo -e "Link gRPC      : ${vmesslink3}" | tee -a /etc/log-create-vmess.log
echo -e "\033[0;34m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m" | tee -a /etc/log-create-vmess.log
echo -e "Expired On     : ${exp}" | tee -a /etc/log-create-vmess.log
echo -e "\033[0;34m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m" | tee -a /etc/log-create-vmess.log
echo ""

read -n 1 -s -r -p "Tekan apa saja untuk kembali ke menu..."

m-vmess
