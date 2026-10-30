# Panel Bot Telegram — AutoscriptXRAY

Bot Telegram untuk mengelola server AutoscriptXRAY dari chat:

- **Buat Akun VMess** — ketik username, pilih masa aktif lewat tombol
  **7 / 15 / 30 hari** atau custom (1–365 hari), lalu pilih batas kuota
  **100 GB / 500 GB / 1 TB / Unlimited**. Bot menjalankan script bawaan
  `/etc/autoscriptvpn/xray/add-vmess.sh` secara non-interaktif dan membalas
  dengan link VMess WS TLS (443), WS NTLS (80), dan gRPC, lengkap dengan
  tanggal expired dari database `/etc/xray/vmess.db`.
- **Status Server** — uptime, RAM, disk, status service Xray & NGINX,
  jumlah akun VMess terdaftar, domain aktif.
- **Daftar Akun** — daftar username VMess + tanggal expired + pemakaian
  kuota (mis. `12.4 GB/100 GB`, `∞` untuk unlimited).

Bot hanya memakai Python 3 standar (tanpa pip install), berjalan dengan
long polling (tidak perlu membuka port / webhook), dan **hanya melayani
ID Telegram yang terdaftar di allowlist** — pesan dari orang lain diabaikan.

## Kuota per akun

Kuota dihitung dari statistik trafik per user milik Xray sendiri
(upload + download digabung), dan ditegakkan oleh `quota-check.py`
yang berjalan tiap 5 menit lewat systemd timer:

- Counter Xray bersifat kumulatif sejak Xray start dan reset setiap
  Xray restart. Checker menyimpan snapshot counter terakhir dan hanya
  menambahkan **delta** ke pemakaian terakumulasi
  (`/var/lib/panelbot/quota-state.json`), jadi restart tidak menghapus
  riwayat pemakaian.
- Begitu pemakaian ≥ kuota: client user dikeluarkan dari config Xray
  (backup + validasi `xray -test` dulu), barisnya dihapus dari
  `vmess.db`, Xray di-restart, dan pemilik server menerima notifikasi
  Telegram.
- Akun **Unlimited** tidak dicatat pemakaiannya sama sekali.
- Akun yang dibuat sebelum fitur kuota ada (atau dari menu panel biasa)
  tidak punya catatan kuota dan tidak diawasi checker.

Fitur kuota butuh statistik per user aktif di Xray. Jalankan sekali:

```bash
bash enable-stats.sh
```

Script itu menambal `/etc/xray/config.json` (blok `stats`/`api`,
policy `statsUserUplink/Downlink`, inbound API di 127.0.0.1:10085),
dengan backup di `/etc/xray/config.json.pre-stats`, validasi
`xray -test`, dan rollback otomatis bila Xray gagal start. Idempotent:
bila sudah aktif, tidak mengubah apa pun. Setelah diaktifkan, counter
mulai menghitung dari 0.

## Cara pasang (di VPS, sebagai root)

```bash
cd ~/AutoscriptXRAY
git pull
cd panelbot
bash install.sh
bash enable-stats.sh
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

- Log bot: `journalctl -u panelbot -f`
- Log pengecek kuota: `journalctl -u quota-check.service`
- Restart bot: `systemctl restart panelbot`
- Update dari repo: `cd ~/AutoscriptXRAY && git pull && cd panelbot && bash install.sh && systemctl restart panelbot`
  (file config di `/etc/panelbot/` tidak ditimpa oleh installer.)

## Keamanan

- Bot berjalan sebagai root karena harus menulis `/etc/xray/config.json`
  lewat script bawaan dan me-restart Xray — karena itu allowlist ID
  adalah pagar utama. Jangan pernah menambahkan ID orang lain.
- Token bot jangan dibagikan; bila bocor, revoke dari @BotFather
  (`/revoke`) dan isi token baru di `config.env`, lalu restart service.
- Inbound API Xray untuk statistik hanya mendengarkan di
  `127.0.0.1:10085` (tidak terbuka ke internet).
- Bot tidak menerima perintah shell bebas; permukaan perintahnya tetap:
  buat akun VMess, status, daftar akun.

## Rencana lanjutan (belum termasuk)

- Protokol lain (VLESS, Trojan, Shadowsocks) — script bawaan
  `add-vless.sh` / `add-trojan.sh` / `add-ssws.sh` polanya sama
  (kuota mengikuti pola yang sama).
- Hapus & perpanjang akun dari bot (`del-vmess.sh`, `renew-vmess.sh`).
- Akun ZIVPN (`/etc/autoscriptvpn/udp/add-zivpn.sh`) — statistik
  trafiknya tidak lewat Xray, jadi kuotanya perlu mekanisme terpisah.
