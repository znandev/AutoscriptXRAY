# Store Bot VPN (bot toko publik)

Bot Telegram publik untuk jualan akun VMess AutoscriptXRAY, meniru pola bot
auto-order: pengguna daftar sendiri, punya saldo, membeli akun dengan saldo,
dan akun dibuat otomatis. Bot ini **terpisah** dari `panelbot/` (bot admin
pribadi). Pembayaran otomatis via gateway **belum** dipakai — top-up bersifat
manual dan dikendalikan admin (keputusan pemilik, 2026-10-31).

## Fitur

- Kartu info pengguna: ID, username, status (Bukan Reseller/Reseller), saldo,
  jumlah transaksi.
- **Buat Akun**: durasi (7/15/30 hari) × kuota (100 GB/500 GB/1 TB/Unlimited),
  harga dari `/etc/storebot/prices.json`, saldo terpotong otomatis.
- **Trial**: akun gratis 1 hari (kuota dari `prices.json` → `trial`), 1× per pengguna.
- **TopUp manual**: pengguna memilih nominal → bot menampilkan info pembayaran
  (`PAYMENT_INFO` di config) → pengguna klik "Saya Sudah Transfer" → admin
  menerima notifikasi berisi tombol **Setujui/Tolak** → saldo terisi otomatis
  saat disetujui.
- **Akun Saya**: daftar akun + tanggal expired + pemakaian kuota (berbagi state
  dengan panelbot: `/var/lib/panelbot/quota-state.json`).
- **Perpanjang**: menambah tanggal expired di `vmess.db`, potong saldo.
- **Hapus Akun**: menghapus akun dari config Xray + vmess.db (tanpa refund).
- **Riwayat**: 10 transaksi terakhir.
- **Jadi Reseller**: pengajuan ke admin; jika disetujui, diskon
  `diskon_reseller_persen` dari `prices.json` berlaku otomatis.
- **Panel Admin** (hanya ID di `ADMIN_IDS`): buka/tutup tiap menu
  (Buat Akun, TopUp, Trial, Perpanjang, Hapus Akun — yang tertutup tampil
  "❌ … Ditutup" seperti bot referensi), persetujuan topup & reseller,
  kredit saldo manual (format: `ID nominal`).

## Install

```bash
cd ~/AutoscriptXRAY   # repo fork ini
git pull
cd storebot
bash install.sh
nano /etc/storebot/config.env   # BOT_TOKEN bot toko, ADMIN_IDS, PAYMENT_INFO
nano /etc/storebot/prices.json  # sesuaikan harga jual
systemctl enable --now storebot
```

Prasyarat: AutoscriptXRAY sudah terinstall, dan statistik kuota panelbot
sudah diaktifkan (`panelbot/enable-stats.sh`) agar pemakaian kuota tampil.

## Harga

Harga bawaan di `prices.json` repo ini adalah **harga contoh sementara**.
Struktur: `harga[hari][label kuota]`, label kuota harus sama dengan kunci di
`kuota` (nilai byte, `null` = unlimited). File di VPS
(`/etc/storebot/prices.json`) dibaca ulang setiap transaksi, jadi perubahan
harga langsung berlaku tanpa restart.

## Data

- Database SQLite: `/var/lib/storebot/store.db` (pengguna, saldo, pesanan,
  topup, riwayat, pengaturan buka/tutup).
- Config: `/etc/storebot/config.env` (chmod 600, berisi token — jangan commit).
