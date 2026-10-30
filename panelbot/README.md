# Panel Bot Telegram — AutoscriptXRAY

Bot Telegram untuk mengelola server AutoscriptXRAY dari chat:

- **Buat Akun VMess** — ketik username, pilih masa aktif lewat tombol
  **7 / 15 / 30 hari** atau custom (1–365 hari). Bot menjalankan script
  bawaan `/etc/autoscriptvpn/xray/add-vmess.sh` secara non-interaktif dan
  membalas dengan link VMess WS TLS (443), WS NTLS (80), dan gRPC,
  lengkap dengan tanggal expired dari database `/etc/xray/vmess.db`.
- **Status Server** — uptime, RAM, disk, status service Xray & NGINX,
  jumlah akun VMess terdaftar, domain aktif.
- **Daftar Akun** — daftar username VMess + tanggal expired.

Bot hanya memakai Python 3 standar (tanpa pip install), berjalan dengan
long polling (tidak perlu membuka port / webhook), dan **hanya melayani
ID Telegram yang terdaftar di allowlist** — pesan dari orang lain diabaikan.

## Cara pasang (di VPS, sebagai root)

```bash
cd ~/AutoscriptXRAY
git pull
cd panelbot
bash install.sh
```

Lalu:

1. Buat bot lewat [@BotFather](https://t.me/BotFather) (`/newbot`), salin tokennya.
2. Isi token dan ID Telegram kamu (cek ID di [@userinfobot](https://t.me/userinfobot)):

   ```bash
   nano /etc/panelbot/config.env
   ```

   ```
   BOT_TOKEN=123456:ABC-DEF...
   ALLOWED_IDS=7652113800
   ```

   File ini hanya ada di VPS (chmod 600) dan **tidak** masuk repo.
3. Nyalakan:

   ```bash
   systemctl enable --now panelbot
   systemctl status panelbot
   ```

4. Buka bot di Telegram, kirim `/start`, pilih menu.

## Operasional

- Log: `journalctl -u panelbot -f`
- Restart: `systemctl restart panelbot`
- Update dari repo: `cd ~/AutoscriptXRAY && git pull && cd panelbot && bash install.sh && systemctl restart panelbot`
  (file config di `/etc/panelbot/` tidak ditimpa oleh installer.)

## Keamanan

- Bot berjalan sebagai root karena harus menulis `/etc/xray/config.json`
  lewat script bawaan dan me-restart Xray — karena itu allowlist ID
  adalah pagar utama. Jangan pernah menambahkan ID orang lain.
- Token bot jangan dibagikan; bila bocor, revoke dari @BotFather
  (`/revoke`) dan isi token baru di `config.env`, lalu restart service.
- Bot tidak menerima perintah shell bebas; permukaan perintahnya tetap:
  buat akun VMess, status, daftar akun.

## Rencana lanjutan (belum termasuk di v1)

- Protokol lain (VLESS, Trojan, Shadowsocks) — script bawaan
  `add-vless.sh` / `add-trojan.sh` / `add-ssws.sh` polanya sama.
- Hapus & perpanjang akun dari bot (`del-vmess.sh`, `renew-vmess.sh`).
- Akun ZIVPN (`/etc/autoscriptvpn/udp/add-zivpn.sh`).
