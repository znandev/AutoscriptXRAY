# SlowDNS (DNSTT) — add-on AutoscriptXRAY

Terowongan DNS (DNSTT, public domain — David Fifield) untuk VPS ini.
Client (aplikasi SlowDNS di Android) terhubung lewat query DNS ke
`slow.slowaethernal.eu.cc`, lalu tunnel diteruskan ke SSH di VPS
(`127.0.0.1:22`). Akun yang dipakai = akun SSH biasa dari menu.

## 1. DNS dulu (Cloudflare, sekali saja)

Di zone `slowaethernal.eu.cc`, tambah 2 record — keduanya **DNS only**:

| Type | Name | Content |
|------|------|---------|
| A | `dns` | `213.163.201.138` |
| NS | `slow` | `dns.slowaethernal.eu.cc` |

Tunggu sampai delegasinya aktif. Cek dari mana saja:

```
nslookup slow.slowaethernal.eu.cc
# harus menjawab: dns.slowaethernal.eu.cc
nslookup dns.slowaethernal.eu.cc
# harus menjawab: 213.163.201.138
```

## 2. Install di VPS

```bash
cd ~/AutoscriptXRAY
git pull
sudo bash slowdns/install-slowdns.sh
```

Opsional: ganti nama zone NS dengan argumen, mis.
`sudo bash slowdns/install-slowdns.sh slow2.slowaethernal.eu.cc`
(pastikan record NS di Cloudflare ikut disesuaikan).

Di akhir install akan tampil **Nameserver** + **Public key** — catat keduanya.
Tersimpan juga di `/etc/slowdns/info.txt`
(lihat dengan `cat /etc/slowdns/info.txt`).
Kunci privat (`/etc/slowdns/server.key`) **TIDAK BOLEH** dibagikan.

Cek service: `systemctl status dnstt` — harus `active (running)`.
Log bila ada masalah: `journalctl -u dnstt -n 50 --no-pager`.

## 3. Buat akun SlowDNS

Dari shell VPS (sebagai root):

```
m-slowdns
```

Isi username, password, dan masa aktif (hari). Script membuat user SSH
dan menampilkan Nameserver + Public key + detail akun — itulah yang
dimasukkan ke aplikasi SlowDNS. Perintah `m-slowdns` dipasang otomatis
oleh `install-slowdns.sh` ke `/usr/bin/m-slowdns`.

## 4. Client (aplikasi SlowDNS)

- Nameserver: `slow.slowaethernal.eu.cc`
- Public key: isi dari `/etc/slowdns/info.txt`
- Akun: akun SSH yang dibuat lewat menu `[1] SSH` (username + password)
- DNS server di aplikasi (bila diminta): `213.163.201.138`

## 4. Hapus

```bash
sudo bash slowdns/uninstall-slowdns.sh
```

Menghapus service, binary, kunci, dan drop-in resolved.
Install ulang = kunci baru = client harus update public key.

## Catatan

- `dnstt-server` di-build dari source upstream
  (https://www.bamsoftware.com/software/dnstt/) dengan Go —
  butuh internet saat install.
- Installer mematikan stub listener systemd-resolved (lewat drop-in
  `/etc/systemd/resolved.conf.d/slowdns.conf`) supaya UDP 53 bebas
  dipakai dnstt. Menghapus drop-in + restart resolved mengembalikannya.
- Port UDP 53 harus bebas dan tidak diblokir provider.
- Script ini tidak me-reboot VPS dan tidak mengubah konfigurasi
  Xray / Nginx / panel yang sudah jalan.
