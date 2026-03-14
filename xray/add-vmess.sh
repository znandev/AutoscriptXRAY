#!/bin/bash

clear
echo -e "\033[0;34m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m"
echo -e "\E[44;1;39m        Add VMess Account        \E[0m"
echo -e "\033[0;34m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m"

# ambil domain
domain=$(cat /etc/xray/domain)

# ambil port dari log install
tls=$(grep -w "XRAY TLS" /root/log-install.txt | cut -d: -f2 | tr -d ' ')
none=$(grep -w "XRAY None TLS" /root/log-install.txt | cut -d: -f2 | tr -d ' ')

read -rp "Username : " user
read -rp "Expired (days): " masaaktif

uuid=$(cat /proc/sys/kernel/random/uuid)
exp=$(date -d "$masaaktif days" +"%Y-%m-%d")

# inject user ke config
jq --arg uuid "$uuid" --arg user "$user" '
(.inbounds[] | select(.tag=="vmess-tls").settings.clients) +=
[{"id":$uuid,"alterId":0,"email":$user}] |
(.inbounds[] | select(.tag=="vmess-nontls").settings.clients) +=
[{"id":$uuid,"alterId":0,"email":$user}]
' /etc/xray/config.json > /tmp/config.json

mv /tmp/config.json /etc/xray/config.json

# generate vmess link
vmesslink1="vmess://$(echo -n "{\"v\":\"2\",\"ps\":\"${user}\",\"add\":\"${domain}\",\"port\":\"${tls}\",\"id\":\"${uuid}\",\"aid\":\"0\",\"net\":\"ws\",\"path\":\"/vmess\",\"type\":\"none\",\"host\":\"${domain}\",\"tls\":\"tls\"}" | base64 -w 0)"

vmesslink2="vmess://$(echo -n "{\"v\":\"2\",\"ps\":\"${user}\",\"add\":\"${domain}\",\"port\":\"${none}\",\"id\":\"${uuid}\",\"aid\":\"0\",\"net\":\"ws\",\"path\":\"/vmess\",\"type\":\"none\",\"host\":\"${domain}\",\"tls\":\"none\"}" | base64 -w 0)"

vmesslink3="vmess://${uuid}@${domain}:${tls}?mode=gun&security=tls&type=grpc&serviceName=vmess-grpc&sni=bug.com#${user}"

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
