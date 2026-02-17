# Supabase Bileşenlerini Local Build Eden Script
# Kullanım: .\build-all.ps1 [service1] [service2] ...
# Örnek: .\build-all.ps1 studio auth  (sadece studio ve auth build eder)
# Örnek: .\build-all.ps1              (tüm servisleri build eder)

param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Services
)

$ErrorActionPreference = "Stop"
$baseDir = Split-Path $PSScriptRoot -Parent

Write-Host "=== Supabase Local Build ===" -ForegroundColor Cyan
Write-Host "Calisma dizini: $baseDir" -ForegroundColor Gray
Write-Host ""

# Tüm servisler
$allServices = @(
    "studio",
    "kong", 
    "auth",
    "rest",
    "realtime",
    "storage",
    "imgproxy",
    "meta",
    "functions",
    "analytics",
    "db",
    "vector",
    "supavisor"
)

# Hangi servisleri build edeceğiz
if ($Services.Count -eq 0) {
    $targetServices = $allServices
    Write-Host "Tum servisler build edilecek..." -ForegroundColor Yellow
} else {
    $targetServices = $Services
    Write-Host "Secilen servisler build edilecek: $($targetServices -join ', ')" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Tahmini toplam sure: ~30-60 dakika (ilk build)" -ForegroundColor Magenta
Write-Host ""

# Build başlat
Push-Location $baseDir

try {
    $buildArgs = @(
        "compose",
        "-f", "docker-compose.yml",
        "-f", "docker-compose.local.yml",
        "build"
    ) + $targetServices

    Write-Host "Calistirilan komut: docker $($buildArgs -join ' ')" -ForegroundColor Gray
    Write-Host ""

    & docker @buildArgs

    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "=== Build basariyla tamamlandi! ===" -ForegroundColor Green
        Write-Host ""
        Write-Host "Olusturulan image'lar:" -ForegroundColor Cyan
        docker images | Select-String "supabase-|local"
        Write-Host ""
        Write-Host "Calistirmak icin:" -ForegroundColor Yellow
        Write-Host "  docker compose -f docker-compose.yml -f docker-compose.local.yml up -d" -ForegroundColor White
    } else {
        Write-Host ""
        Write-Host "=== Build hatasi olustu! ===" -ForegroundColor Red
        exit 1
    }
} finally {
    Pop-Location
}
