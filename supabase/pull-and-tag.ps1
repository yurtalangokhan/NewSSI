# Supabase Imagelarini Pull Edip Local Tag'leyen Script
# Bu yontem en hizli ve en guvenilir yontemdir
# Kullanım: .\pull-and-tag.ps1

$ErrorActionPreference = "Stop"

Write-Host "=== Supabase Image'lari Pull ve Tag Ediliyor ===" -ForegroundColor Cyan

# Image listesi: Original -> Local tag
$images = @(
    @{ Original = "supabase/studio:2025.12.17-sha-43f4f7f"; Local = "supabase-studio:local" },
    @{ Original = "kong:2.8.1"; Local = "supabase-kong:local" },
    @{ Original = "supabase/gotrue:v2.184.0"; Local = "supabase-auth:local" },
    @{ Original = "postgrest/postgrest:v14.1"; Local = "supabase-rest:local" },
    @{ Original = "supabase/realtime:v2.68.0"; Local = "supabase-realtime:local" },
    @{ Original = "supabase/storage-api:v1.33.0"; Local = "supabase-storage:local" },
    @{ Original = "darthsim/imgproxy:v3.8.0"; Local = "supabase-imgproxy:local" },
    @{ Original = "supabase/postgres-meta:v0.95.1"; Local = "supabase-meta:local" },
    @{ Original = "supabase/edge-runtime:v1.69.28"; Local = "supabase-functions:local" },
    @{ Original = "supabase/logflare:1.27.0"; Local = "supabase-analytics:local" },
    @{ Original = "supabase/postgres:15.8.1.085"; Local = "supabase-db:local" },
    @{ Original = "timberio/vector:0.28.1-alpine"; Local = "supabase-vector:local" },
    @{ Original = "supabase/supavisor:2.7.4"; Local = "supabase-pooler:local" }
)

foreach ($img in $images) {
    Write-Host ""
    Write-Host "[$($img.Local)] Pulling $($img.Original)..." -ForegroundColor Yellow
    docker pull $img.Original
    
    Write-Host "[$($img.Local)] Tagging as $($img.Local)..." -ForegroundColor Green
    docker tag $img.Original $img.Local
}

Write-Host ""
Write-Host "=== Tum image'lar basariyla tag'lendi! ===" -ForegroundColor Green
Write-Host ""
Write-Host "Local image'lari gormek icin: docker images | Select-String 'supabase-'" -ForegroundColor Cyan
Write-Host "Calistirmak icin: docker compose -f docker-compose.local-images.yml up -d" -ForegroundColor Cyan
