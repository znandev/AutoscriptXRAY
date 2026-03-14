#!/bin/bash
# Setup Script XRAY_AIO
# XRAY (VLESS, VMess, Trojan) + WireGuard Only

echo "" > /root/log-install.txt
cd "$(dirname "$0")"
rm -f setup.sh
clear

# Warna
red='\e[1;31m'
green='\e[0;32m'
yellow='\e[1;33m'
blue='\e[1;34m'
NC='\e[0m'

# Fungsi warna
function info() { echo -e "${green}[INFO]${NC} $1"; }
function warn() { echo -e "${yellow}[WARNING]${NC} $1"; }
function error() { echo -e "${red}[ERROR]${NC} $1"; }

# Mulai timer
start_time=$(date +%s)

# Check Root
if [ "${EUID}" -ne 0 ]; then
  error "Script harus dijalankan sebagai root."
  exit 1
fi

# Check OpenVZ
if [ "$(systemd-detect-virt)" == "openvz" ]; then
  error "OpenVZ tidak didukung. Gunakan KVM/VMWare."
  exit 1
fi

# Setup /etc/hosts jika belum sesuai
localip=$(hostname -I | awk '{print $1}')
hostname=$(hostname)
domainline=$(grep -w "$hostname" /etc/hosts | awk '{print $2}')
if [[ "$hostname" != "$domainline" ]]; then
  echo "$localip $hostname" >> /etc/hosts
fi

# Create folder yang dibutuhkan
mkdir -p /etc/xray /etc/v2ray /var/lib
for file in domain scdomain; do
  touch /etc/xray/$file
  touch /etc/v2ray/$file
  touch /root/$file
done
touch /var/lib/ipvps.conf

# Set Timezone
ln -fs /usr/share/zoneinfo/Asia/Jakarta /etc/localtime

# Update & Install Dependensi
info "Installing dependencies..."
apt update -y >/dev/null 2>&1
apt install -y curl wget git screen unzip bzip2 gzip coreutils python3 python3-pip >/dev/null 2>&1

# Header Linux
kernelver=$(uname -r)
headerpkg="linux-headers-$kernelver"
if ! dpkg -s $headerpkg >/dev/null 2>&1; then
  info "Installing $headerpkg..."
  apt install -y $headerpkg
fi

# Setup Domain
clear
echo -e "$blue========= DOMAIN SETUP =========$NC"
echo ""
read -rp "Masukkan domain kamu: " domain

echo "$domain" > /root/domain

for dfile in domain scdomain; do
  echo "$domain" > /etc/xray/$dfile
  echo "$domain" > /etc/v2ray/$dfile
  echo "$domain" > /root/$dfile
done

echo "IP=$domain" > /var/lib/ipvps.conf

echo ""
echo -e "Domain berhasil diset: $domain"
sleep 2
if [[ -z "$domain" ]]; then
echo "Domain tidak boleh kosong!"
exit 1
fi

# Eksekusi Installer per Fitur
info "Menjalankan installer XRAY..."
bash install/xray.sh
info "Menjalankan installer WireGuard..."
bash install/wg.sh

# Salin sub-menu & tools ke /usr/bin
info "Menyalin command menu..."
cp -f xray/m-vmess /usr/bin/
cp -f xray/m-vless /usr/bin/
cp -f xray/m-trojan /usr/bin/
cp -f xray/m-ssws /usr/bin/
cp -f wg/m-wg /usr/bin/
cp -f tools/tools-menu /usr/bin/
cp -f tools/backup.sh /usr/bin/
cp -f tools/speedtest.sh /usr/bin/
cp -f tools/domain.sh /usr/bin/
cp -f menu.sh /usr/bin/menu

# Set permission eksekusi
chmod +x /usr/bin/*
chmod +x xray/*.sh wg/*.sh tools/*.sh /usr/bin/menu

# Copy semua script ke folder runtime /etc/autoscriptvpn
info "Menyalin semua submenu ke /etc/autoscriptvpn/..."
mkdir -p /etc/autoscriptvpn/{xray,tools,wg}

cp -r xray/*.sh /etc/autoscriptvpn/xray/
cp -r tools/*.sh /etc/autoscriptvpn/tools/
cp -r wg/*.sh /etc/autoscriptvpn/wg/

chmod +x /etc/autoscriptvpn/*/*.sh

# Tambahkan menu otomatis saat login
cat > /root/.profile <<-EOF
if [ "\$BASH" ]; then
  if [ -f ~/.bashrc ]; then
    . ~/.bashrc
  fi
fi
clear
menu
EOF
chmod 644 /root/.profile

# Bersih-bersih file sementara
rm -f cf ins-xray.sh setup.sh

# Tampilkan durasi dan reboot
end_time=$(date +%s)
elapsed=$((end_time - start_time))
echo -e "${green}✅ Instalasi selesai dalam $((elapsed / 60)) menit $((elapsed % 60)) detik.${NC}"
echo -e "${green}♻️ VPS akan reboot dalam 10 detik...${NC}"
sleep 10
reboot
