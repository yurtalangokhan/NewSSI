#!/bin/bash
# Supabase Bileşenlerini Clone Eden Script
# Kullanım: ./clone-repos.sh

set -e
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Supabase Bileşenleri Clone Ediliyor ==="

clone_repo() {
    local name=$1
    local url=$2
    local sparse=$3
    local target="$BASE_DIR/$name"
    
    if [ -d "$target" ]; then
        echo "[$name] Zaten mevcut, guncelleniyor..."
        cd "$target" && git pull --ff-only && cd "$BASE_DIR"
    else
        echo "[$name] Clone ediliyor..."
        if [ -n "$sparse" ]; then
            git clone --filter=blob:none --sparse "$url" "$target"
            cd "$target" && git sparse-checkout set "$sparse" && cd "$BASE_DIR"
        else
            git clone --depth 1 "$url" "$target"
        fi
    fi
}

# Clone all repos
clone_repo "studio" "https://github.com/supabase/supabase.git" "studio"
clone_repo "gotrue" "https://github.com/supabase/gotrue.git" ""
clone_repo "realtime" "https://github.com/supabase/realtime.git" ""
clone_repo "storage-api" "https://github.com/supabase/storage-api.git" ""
clone_repo "postgres-meta" "https://github.com/supabase/postgres-meta.git" ""
clone_repo "edge-runtime" "https://github.com/supabase/edge-runtime.git" ""
clone_repo "logflare" "https://github.com/Logflare/logflare.git" ""
clone_repo "postgres" "https://github.com/supabase/postgres.git" ""
clone_repo "supavisor" "https://github.com/supabase/supavisor.git" ""
clone_repo "postgrest" "https://github.com/PostgREST/postgrest.git" ""
clone_repo "kong" "https://github.com/Kong/kong.git" ""
clone_repo "imgproxy" "https://github.com/imgproxy/imgproxy.git" ""
clone_repo "vector" "https://github.com/vectordotdev/vector.git" ""

echo ""
echo "=== Tum repolar basariyla clone edildi! ==="
echo "Simdi 'docker compose build' komutunu calistirabilirsiniz."
