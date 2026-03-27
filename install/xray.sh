#!/bin/bash
# Setup Xray Core - by znand-dev

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}▶️ Memulai instalasi Xray-core...${NC}"
sleep 1

# Install dependensi
apt update -y
apt install -y socat curl cron jq unzip gnupg coreutils lsof -qq

# Download Xray-core terbaru
mkdir -p /etc/xray /var/log/xray /usr/local/bin

echo -e "${GREEN}⬇️ Download Xray-core...${NC}"
wget -q -O /tmp/xray.zip https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip
unzip -o /tmp/xray.zip -d /usr/local/bin/
chmod +x /usr/local/bin/xray
rm -f /tmp/xray.zip

# Konfigurasi domain
if [[ -f /root/domain ]]; then
  domain=$(cat /root/domain)
else
  echo -e "${RED}[ERROR] File /root/domain tidak ditemukan!${NC}"
  exit 1
fi

echo "$domain" > /etc/xray/domain

# Install acme.sh
if [ ! -f ~/.acme.sh/acme.sh ]; then
  echo -e "${GREEN}🔐 Menginstall acme.sh...${NC}"
  curl https://get.acme.sh | sh -s email=admin@$domain
fi

ACME=~/.acme.sh/acme.sh

chmod +x /root/.acme.sh/acme.sh

/root/.acme.sh/acme.sh --set-default-ca --server letsencrypt
/root/.acme.sh/acme.sh --register-account -m admin@$domain
/root/.acme.sh/acme.sh --issue --standalone -d $domain --keylength ec-256

mkdir -p /etc/xray
/root/.acme.sh/acme.sh --install-cert -d $domain \
  --key-file /etc/xray/private.key \
  --fullchain-file /etc/xray/cert.crt \
  --ecc

# Deploy config.json ke xray (vmess, vless, trojan, ss-ws)
cat > /etc/xray/config.json <<EOF
{
  "log": {
    "access": "/var/log/xray/access.log",
    "error": "/var/log/xray/error.log",
    "loglevel": "warning"
  },
  "inbounds": [
    {
      "port": 443,
      "listen": "0.0.0.0",
      "protocol": "vmess",
      "settings": {
        "clients": []
      },
      "streamSettings": {
        "network": "ws",
        "security": "tls",
        "tlsSettings": {
          "certificates": [
            {
              "certificateFile": "/etc/xray/cert.crt",
              "keyFile": "/etc/xray/private.key"
            }
          ]
        },
        "wsSettings": {
          "path": "/vmess"
        }
      },
      "tag": "vmess-tls"
    },
    {
      "port": 80,
      "listen": "0.0.0.0",
      "protocol": "vmess",
      "settings": {
        "clients": []
      },
      "streamSettings": {
        "network": "ws",
        "security": "none",
        "wsSettings": {
          "path": "/vmess"
        }
      },
      "tag": "vmess-nontls"
    },
    {
      "port": 4443,
      "listen": "0.0.0.0",
      "protocol": "vmess",
      "settings": {
        "clients": []
      },
      "streamSettings": {
        "network": "grpc",
        "security": "tls",
        "tlsSettings": {
          "certificates": [
            {
              "certificateFile": "/etc/xray/cert.crt",
              "keyFile": "/etc/xray/private.key"
            }
          ]
        },
        "grpcSettings": {
          "serviceName": "vmess-grpc"
        }
      },
      "tag": "vmess-grpc"
    },
    {
      "port": 8443,
      "listen": "0.0.0.0",
      "protocol": "vless",
      "settings": {
        "clients": [],
        "decryption": "none"
      },
      "streamSettings": {
        "network": "ws",
        "security": "tls",
        "tlsSettings": {
          "certificates": [
            {
              "certificateFile": "/etc/xray/cert.crt",
              "keyFile": "/etc/xray/private.key"
            }
          ]
        },
        "wsSettings": {
          "path": "/vless"
        }
      },
      "tag": "vless-tls"
    },
    {
      "port": 8080,
      "listen": "0.0.0.0",
      "protocol": "vless",
      "settings": {
        "clients": [],
        "decryption": "none"
      },
      "streamSettings": {
        "network": "ws",
        "security": "none",
        "wsSettings": {
          "path": "/vless"
        }
      },
      "tag": "vless-nontls"
    },
    {
      "port": 8444,
      "listen": "0.0.0.0",
      "protocol": "vless",
      "settings": {
        "clients": [],
        "decryption": "none"
      },
      "streamSettings": {
        "network": "grpc",
        "security": "tls",
        "tlsSettings": {
          "certificates": [
            {
              "certificateFile": "/etc/xray/cert.crt",
              "keyFile": "/etc/xray/private.key"
            }
          ]
        },
        "grpcSettings": {
          "serviceName": "vless-grpc"
        }
      },
      "tag": "vless-grpc"
    },
    {
      "port": 2083,
      "listen": "0.0.0.0",
      "protocol": "trojan",
      "settings": {
        "clients": []
      },
      "streamSettings": {
        "network": "ws",
        "security": "tls",
        "tlsSettings": {
          "certificates": [
            {
              "certificateFile": "/etc/xray/cert.crt",
              "keyFile": "/etc/xray/private.key"
            }
          ]
        },
        "wsSettings": {
          "path": "/trojan"
        }
      },
      "tag": "trojan-tls"
    },
    {
      "port": 2084,
      "listen": "0.0.0.0",
      "protocol": "trojan",
      "settings": {
        "clients": []
      },
      "streamSettings": {
        "network": "grpc",
        "security": "tls",
        "tlsSettings": {
          "certificates": [
            {
              "certificateFile": "/etc/xray/cert.crt",
              "keyFile": "/etc/xray/private.key"
            }
          ]
        },
        "grpcSettings": {
          "serviceName": "trojan-grpc"
        }
      },
      "tag": "trojan-grpc"
    },
    {
      "port": 9443,
      "listen": "0.0.0.0",
      "protocol": "shadowsocks",
      "settings": {
        "method": "aes-128-gcm",
        "clients": [
          #ssws
        ]
      },
      "streamSettings": {
        "network": "ws",
        "security": "tls",
        "tlsSettings": {
          "certificates": [
            {
              "certificateFile": "/etc/xray/cert.crt",
              "keyFile": "/etc/xray/private.key"
            }
          ]
        },
        "wsSettings": {
          "path": "/ss-ws"
        }
      },
      "tag": "ssws-tls"
    },
    {
      "port": 9080,
      "listen": "0.0.0.0",
      "protocol": "shadowsocks",
      "settings": {
        "method": "aes-128-gcm",
        "clients": [
          #ssws
        ]
      },
      "streamSettings": {
        "network": "ws",
        "security": "none",
        "wsSettings": {
          "path": "/ss-ws"
        }
      },
      "tag": "ssws-nontls"
    }
  ],
  "outbounds": [
    {
      "protocol": "freedom",
      "tag": "direct"
    },
    {
      "protocol": "blackhole",
      "tag": "blocked"
    }
  ]
}
EOF

# Setup systemd service
cat > /etc/systemd/system/xray.service <<EOF
[Unit]
Description=Xray Service
Documentation=https://xray.dev/
After=network.target nss-lookup.target

[Service]
User=root
NoNewPrivileges=true
ExecStart=/usr/local/bin/xray -config /etc/xray/config.json
Restart=on-failure
LimitNPROC=1000000
LimitNOFILE=1000000

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable xray

# Tambahkan info ke log install (setiap protocol port unik)
cat > /root/log-install.txt <<'LOGEOF'
XRAY VMess TLS      : 443
XRAY VMess None TLS : 80
XRAY VMess gRPC     : 4443
XRAY VLESS TLS      : 8443
XRAY VLESS None TLS : 8080
XRAY VLESS gRPC     : 8444
XRAY Trojan TLS     : 2083
XRAY Trojan gRPC    : 2084
XRAY SS WS TLS      : 9443
XRAY SS WS none TLS : 9080
LOGEOF

# Output final
echo -e "${GREEN}✅ Xray-core berhasil di-install dan dikonfigurasi!${NC}"
echo -e "${GREEN}📂 Config: /etc/xray/config.json${NC}"
echo -e "${GREEN}🔐 Domain: $domain${NC}"
echo -e "${GREEN}🚀 Jalankan dengan: systemctl start xray${NC}"
