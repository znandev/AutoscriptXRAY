#!/bin/bash
# Uninstall Script - Autoscript by znandev

RED='\033[1;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

confirm() {
  read -p "❗ Yakin ingin menghapus semua layanan AutoscriptXRAY? [y/N]: " confirm
  [[ "$confirm" == "y" || "$confirm" == "Y" ]] || { echo "Batal uninstall."; exit 1; }
}

info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1"; }

confirm
echo -e "${YELLOW}🚮 Menghapus layanan AutoscriptXRAY...${NC}"

# 1. Hentikan service terkait
services=(xray xray@trojan xray@vless xray@vmess sshws stunnel4 dropbear)
for svc in "${services[@]}"; do
  systemctl stop $svc >/dev/null 2>&1
  systemctl disable $svc >/dev/null 2>&1
done

# 2. Hapus file dan folder konfigurasi
rm -rf /etc/autoscriptvpn
rm -rf /etc/xray /etc/v2ray
rm -rf /var/lib/ipvps.conf
rm -f /root/domain /root/scdomain
rm -f /root/log-install.txt /etc/log-create-ssh.log

# 3. Hapus binary & script dari /usr/bin
binaries=(
  menu m-sshovpn m-vmess m-vless m-trojan m-ssws m-wg tools-menu
  trial-ssh backup.sh speedtest.sh domain.sh
  restart-ws.sh stop-ws.sh service-install.sh
)

for bin in "${binaries[@]}"; do
  rm -f /usr/bin/$bin
done

# 4. Hapus user SSH trial* (opsional)
info "Menghapus user trial*..."
for u in $(awk -F: '/^trial/ {print $1}' /etc/passwd); do
  userdel -f $u >/dev/null 2>&1
done

# 5. Opsional: hapus file repo (jika dijalankan dari folder Autoscript)
rm -rf ~/AutoscriptXRAY

echo -e "${GREEN}✅ SIGMA VPN berhasil dihapus.${NC}"
echo -e "💡 Reboot VPS disarankan: ${YELLOW}reboot${NC}"
