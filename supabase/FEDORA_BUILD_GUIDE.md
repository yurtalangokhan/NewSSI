# Supabase Postgres - Fedora Build Guide

Bu rehber, Supabase Postgres Docker image'ını Fedora'da build edip Windows'a aktarmanızı sağlar.

---

## 📋 Ön Gereksinimler (Fedora)

### 1. Docker Kurulumu

```bash
# Docker'ı kur
sudo dnf -y install dnf-plugins-core
sudo dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Docker servisini başlat
sudo systemctl start docker
sudo systemctl enable docker

# Kullanıcıyı docker grubuna ekle (sudo olmadan çalıştırmak için)
sudo usermod -aG docker $USER

# Oturumu yeniden aç veya:
newgrp docker

# Test et
docker run hello-world
```

### 2. Git Kurulumu (yoksa)

```bash
sudo dnf install -y git
```

---

## 🚀 Build İşlemi

### Adım 1: Çalışma Dizini Oluştur

```bash
mkdir -p ~/supabase-build && cd ~/supabase-build
```

### Adım 2: Supabase Postgres Reposunu Clone Et

```bash
git clone --depth 1 https://github.com/supabase/postgres.git
cd postgres
```

### Adım 3: Build Al (PostgreSQL 15)

```bash
# Build işlemi (bu uzun sürebilir, ~30-60 dakika)
docker build -t supabase-db:local -f Dockerfile-15 .

# Build durumunu kontrol et
docker images | grep supabase-db
```

### Adım 4: Build Tamamlandığında Image Boyutunu Kontrol Et

```bash
docker images supabase-db:local --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
```

---

## 📦 Image'ı Export Et (Fedora → Windows Transfer)

### Seçenek A: TAR Dosyası Olarak Export (Önerilen)

```bash
# Image'ı tar dosyasına kaydet
docker save supabase-db:local -o ~/supabase-db-local.tar

# Dosya boyutunu kontrol et
ls -lh ~/supabase-db-local.tar

# Sıkıştırılmış versiyon (daha küçük boyut, daha uzun süre)
docker save supabase-db:local | gzip > ~/supabase-db-local.tar.gz

# Sıkıştırılmış dosya boyutu
ls -lh ~/supabase-db-local.tar.gz
```

### Seçenek B: USB/Harici Disk'e Kopyala

```bash
# USB mount edilmişse (örn: /run/media/$USER/USB_NAME)
cp ~/supabase-db-local.tar /run/media/$USER/USB_NAME/

# veya sıkıştırılmış versiyonu
cp ~/supabase-db-local.tar.gz /run/media/$USER/USB_NAME/
```

### Seçenek C: Ağ Üzerinden Transfer (aynı ağda ise)

```bash
# Fedora'da - Python HTTP server başlat
cd ~ && python3 -m http.server 8888

# Windows'ta tarayıcıdan indir:
# http://FEDORA_IP:8888/supabase-db-local.tar.gz
```

---

## 💻 Windows'ta Image'ı Import Et

### PowerShell'de:

```powershell
# Dosyanın bulunduğu dizine git
cd C:\Users\Burak\Downloads  # veya dosyanın olduğu yer

# TAR dosyasından import et
docker load -i supabase-db-local.tar

# veya sıkıştırılmış versiyondan
docker load -i supabase-db-local.tar.gz

# Import edilen image'ı kontrol et
docker images | findstr supabase-db
```

### Doğrulama

```powershell
# Image'ın düzgün yüklendiğini kontrol et
docker inspect supabase-db:local --format '{{.Id}}'

# Test çalıştır
docker run --rm supabase-db:local postgres --version
```

---

## 🔧 docker-compose.local-images.yml ile Kullanım

Windows'ta import işleminden sonra, mevcut docker-compose dosyanız zaten `supabase-db:local` image'ını kullanacak şekilde ayarlı:

```powershell
cd C:\Users\Burak\Desktop\Masaustu\Projeler\langchain-dockerized\supabase\docker

# Tüm servisleri başlat
docker compose -f docker-compose.yml -f docker-compose.local-images.yml up -d

# Sadece db'yi başlat
docker compose -f docker-compose.yml -f docker-compose.local-images.yml up db -d
```

---

## 🛠️ Sorun Giderme

### Build Hatası: Nix İndirme Sorunu

```bash
# Nix cache'i temizle ve tekrar dene
docker builder prune -a
docker build --no-cache -t supabase-db:local -f Dockerfile-15 .
```

### Import Hatası: "no space left on device"

```powershell
# Docker'da yer aç
docker system prune -a

# Tekrar import et
docker load -i supabase-db-local.tar
```

### Image Hash Uyumsuzluğu

```powershell
# Eski image'ı sil
docker rmi supabase-db:local

# Tekrar import et
docker load -i supabase-db-local.tar
```

---

## 📊 Beklenen Sonuçlar

| Metrik | Değer |
|--------|-------|
| Build Süresi | ~30-60 dakika |
| Image Boyutu | ~2-3 GB |
| TAR Dosyası | ~1.5-2.5 GB |
| Sıkıştırılmış TAR | ~800 MB - 1.2 GB |

---

## ✅ Hızlı Komut Listesi (Kopyala-Yapıştır)

### Fedora - Tek Seferde Tümü

```bash
# Kurulum ve Build (ilk kez)
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin git
sudo systemctl start docker && sudo systemctl enable docker
sudo usermod -aG docker $USER && newgrp docker

# Clone ve Build
mkdir -p ~/supabase-build && cd ~/supabase-build
git clone --depth 1 https://github.com/supabase/postgres.git
cd postgres
docker build -t supabase-db:local -f Dockerfile-15 .

# Export
docker save supabase-db:local | gzip > ~/supabase-db-local.tar.gz
echo "Dosya: ~/supabase-db-local.tar.gz"
ls -lh ~/supabase-db-local.tar.gz
```

### Windows - Import

```powershell
# Import et (dosya yolunu değiştir)
docker load -i "C:\path\to\supabase-db-local.tar.gz"

# Kontrol et
docker images supabase-db:local
```

---

## 📝 Notlar

- Build sırasında internet bağlantısı gerekli (Nix paketleri indirilecek)
- Fedora'da en az 20 GB boş disk alanı olmalı
- Build süresi internet hızına ve CPU'ya bağlı
- Sıkıştırılmış TAR transferi daha hızlı olur
