# Supabase Bileşenlerini Clone Eden Script
# Kullanım: .\clone-repos.ps1

$ErrorActionPreference = "Stop"
$baseDir = $PSScriptRoot

Write-Host "=== Supabase Bileşenleri Clone Ediliyor ===" -ForegroundColor Cyan

# Repo listesi
$repos = @(
    @{ Name = "studio"; Url = "https://github.com/supabase/supabase.git"; Sparse = "studio" },
    @{ Name = "gotrue"; Url = "https://github.com/supabase/gotrue.git"; Sparse = $null },
    @{ Name = "realtime"; Url = "https://github.com/supabase/realtime.git"; Sparse = $null },
    @{ Name = "storage-api"; Url = "https://github.com/supabase/storage-api.git"; Sparse = $null },
    @{ Name = "postgres-meta"; Url = "https://github.com/supabase/postgres-meta.git"; Sparse = $null },
    @{ Name = "edge-runtime"; Url = "https://github.com/supabase/edge-runtime.git"; Sparse = $null },
    @{ Name = "logflare"; Url = "https://github.com/Logflare/logflare.git"; Sparse = $null },
    @{ Name = "postgres"; Url = "https://github.com/supabase/postgres.git"; Sparse = $null },
    @{ Name = "supavisor"; Url = "https://github.com/supabase/supavisor.git"; Sparse = $null },
    @{ Name = "postgrest"; Url = "https://github.com/PostgREST/postgrest.git"; Sparse = $null },
    @{ Name = "kong"; Url = "https://github.com/Kong/kong.git"; Sparse = $null },
    @{ Name = "imgproxy"; Url = "https://github.com/imgproxy/imgproxy.git"; Sparse = $null },
    @{ Name = "vector"; Url = "https://github.com/vectordotdev/vector.git"; Sparse = $null }
)

foreach ($repo in $repos) {
    $targetDir = Join-Path $baseDir $repo.Name
    
    if (Test-Path $targetDir) {
        Write-Host "[$($repo.Name)] Zaten mevcut, guncelleniyor..." -ForegroundColor Yellow
        Push-Location $targetDir
        git pull --ff-only
        Pop-Location
    } else {
        Write-Host "[$($repo.Name)] Clone ediliyor..." -ForegroundColor Green
        
        if ($repo.Sparse) {
            # Sparse checkout for monorepo (supabase/supabase -> studio)
            git clone --filter=blob:none --sparse $repo.Url $targetDir
            Push-Location $targetDir
            git sparse-checkout set $repo.Sparse
            Pop-Location
        } else {
            git clone --depth 1 $repo.Url $targetDir
        }
    }
}

Write-Host ""
Write-Host "=== Tum repolar basariyla clone edildi! ===" -ForegroundColor Green
Write-Host "Simdi 'docker compose build' komutunu calistirabilirsiniz." -ForegroundColor Cyan
