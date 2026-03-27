#!/bin/bash
MYIP=$(wget -qO- ipv4.icanhazip.com);
echo "Checking VPS"
clear
source /var/lib/ipvps.conf
if [[ "$IP" = "" ]]; then
  domain=$(cat /etc/xray/domain)
else
  domain=$IP
fi

port_tls=$(cat ~/log-install.txt | grep -w "XRAY SS WS TLS" | cut -d: -f2 | sed 's/ //g')
port_none=$(cat ~/log-install.txt | grep -w "XRAY SS WS none TLS" | cut -d: -f2 | sed 's/ //g')

until [[ $user =~ ^[a-zA-Z0-9_]+$ && ${CLIENT_EXISTS} == '0' ]]; do
  echo -e "\033[0;34m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m"
  echo -e "\E[44;1;39m     Add Shadowsocks Account     \E[0m"
  echo -e "\033[0;34m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m"
  read -rp "User: " -e user
  CLIENT_EXISTS=$(grep -w "\"$user\"" /etc/xray/config.json | wc -l)

  if [[ ${CLIENT_EXISTS} == '1' ]]; then
    clear
    echo -e "\033[0;34m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m"
    echo -e "\E[44;1;39m     Add Shadowsocks Account     \E[0m"
    echo -e "\033[0;34m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m"
    echo ""
    echo "A client with the specified name was already created, please choose another name."
    echo ""
    read -n 1 -s -r -p "Press any key to back on menu"
    m-ssws
  fi
done

cipher="aes-128-gcm"
uuid=$(cat /proc/sys/kernel/random/uuid)
read -p "Expired (days): " masaaktif
exp=$(date -d "$masaaktif days" +"%Y-%m-%d")

# inject user ke config SS WS (marker: #ssws)
sed -i 's/#ssws$/#ssws\n#ssws '"$user $exp"'\n    },{"password": "'"$uuid"'", "method": "'"$cipher"'", "email": "'"$user"'"\n#ssws/' /etc/xray/config.json

sslink1="ss://$(echo -n "$cipher:$uuid" | base64 -w0)@$domain:$port_tls?plugin=xray-plugin;path=/ss-ws;host=$domain;tls#${user}"
sslink2="ss://$(echo -n "$cipher:$uuid" | base64 -w0)@$domain:$port_none?plugin=xray-plugin;path=/ss-ws;host=$domain#${user}"

systemctl restart xray

clear
echo -e "\033[0;34m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m" | tee -a /etc/log-create-ssws.log
echo -e "\E[44;1;39m      Shadowsocks Account       \E[0m" | tee -a /etc/log-create-ssws.log
echo -e "\033[0;34m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m" | tee -a /etc/log-create-ssws.log
echo -e "Remarks       : ${user}" | tee -a /etc/log-create-ssws.log
echo -e "Domain        : ${domain}" | tee -a /etc/log-create-ssws.log
echo -e "Port TLS      : $port_tls" | tee -a /etc/log-create-ssws.log
echo -e "Port No TLS   : $port_none" | tee -a /etc/log-create-ssws.log
echo -e "Password      : ${uuid}" | tee -a /etc/log-create-ssws.log
echo -e "Cipher        : ${cipher}" | tee -a /etc/log-create-ssws.log
echo -e "Network       : ws" | tee -a /etc/log-create-ssws.log
echo -e "Path          : /ss-ws" | tee -a /etc/log-create-ssws.log
echo -e "Expired On    : $exp" | tee -a /etc/log-create-ssws.log
echo -e "\033[0;34m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m" | tee -a /etc/log-create-ssws.log
echo -e "Link TLS      : ${sslink1}" | tee -a /etc/log-create-ssws.log
echo -e "\033[0;34m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m" | tee -a /etc/log-create-ssws.log
echo -e "Link None TLS : ${sslink2}" | tee -a /etc/log-create-ssws.log
echo -e "\033[0;34m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m" | tee -a /etc/log-create-ssws.log
echo "" | tee -a /etc/log-create-ssws.log
read -n 1 -s -r -p "Press any key to back on menu"

m-ssws
