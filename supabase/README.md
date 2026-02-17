# Supabase Local Build Guide
# ============================

Bu klasör Supabase bileşenlerini local olarak build etmek için gerekli dosyaları içerir.

## Hızlı Başlangıç

### 1. Repo'ları Clone Edin

```powershell
cd builds
.\clone-repos.ps1
```

veya Linux/Mac:
```bash
cd builds
chmod +x clone-repos.sh
./clone-repos.sh
```

### 2. Build ve Çalıştırma

```bash
cd ..
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build
```

## Bileşen Listesi

| Bileşen | Teknoloji | Build Süresi | Zorluk |
|---------|-----------|--------------|--------|
| studio | Next.js | ~5 dk | Kolay |
| auth (gotrue) | Go | ~3 dk | Kolay |
| rest (postgrest) | Haskell | ~30 dk | Zor* |
| realtime | Elixir | ~10 dk | Orta |
| storage | Node.js | ~3 dk | Kolay |
| meta | Node.js | ~2 dk | Kolay |
| functions | Deno/Rust | ~15 dk | Orta |
| analytics | Elixir | ~10 dk | Orta |
| db | PostgreSQL | ~5 dk | Kolay |
| vector | Rust | ~20 dk | Zor* |
| supavisor | Elixir | ~10 dk | Orta |
| imgproxy | Go | ~5 dk | Kolay |
| kong | Go/Lua | ~10 dk | Orta |

*: Pre-built binary kullanılması önerilir

## Sadece Belirli Bileşenleri Build Etme

Sadece belirli servisleri build etmek için:

```bash
# Sadece studio ve auth build et
docker compose -f docker-compose.yml -f docker-compose.local.yml build studio auth

# Build edip çalıştır
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build studio auth
```

## Sorun Giderme

### Build Hataları

1. **Node.js bileşenleri (studio, storage, meta)**
   - Node 18+ gerekli
   - `npm ci` hatası: `rm -rf node_modules && npm install`

2. **Go bileşenleri (auth, imgproxy)**
   - Go 1.21+ gerekli
   - Proxy ayarları: `GOPROXY=https://proxy.golang.org`

3. **Elixir bileşenleri (realtime, analytics, supavisor)**
   - Elixir 1.15+ / OTP 26+ gerekli
   - Mix deps: `mix deps.get`

4. **Rust bileşenleri (vector, edge-runtime)**
   - Rust 1.70+ gerekli
   - Çok uzun sürer, pre-built önerilir

### Memory Issues

Docker Desktop'ta memory limitini artırın:
- Settings > Resources > Memory: en az 8GB

### Disk Space

Tüm repo'lar + build cache: ~20GB gerekli

## Özelleştirme

Her bileşeni özelleştirmek için:

1. İlgili klasördeki kaynak kodu değiştirin
2. `docker compose build <service-name>` ile yeniden build edin
3. Test edin

## Versiyon Yönetimi

Belirli bir versiyonu build etmek için:

```bash
cd builds/gotrue
git checkout v2.184.0
cd ../..
docker compose -f docker-compose.yml -f docker-compose.local.yml build auth
```
