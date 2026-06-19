#!/usr/bin/env bash
# =============================================================================
# infra/minio/create-buckets.sh
# MinIO bucket'larini birinchi deployda yaratish skripti
#
# FOYDALANISH:
#   # MinIO konteyner ishga tushgandan so'ng:
#   MINIO_ROOT_USER=minioadmin \
#   MINIO_ROOT_PASSWORD=<parol> \
#   MINIO_ENDPOINT=http://minio:9000 \
#     bash infra/minio/create-buckets.sh
#
#   # Yoki Docker orqali (to'g'ridan-to'g'ri):
#   docker run --rm --network retail_default \
#     -e MINIO_ROOT_USER=minioadmin \
#     -e MINIO_ROOT_PASSWORD=<parol> \
#     -v "$(pwd)/infra/minio/create-buckets.sh:/create-buckets.sh" \
#     minio/mc:latest \
#     sh /create-buckets.sh
#
# TALABLAR:
#   mc (MinIO Client) o'rnatilgan bo'lishi kerak.
#   https://min.io/docs/minio/linux/reference/minio-mc.html
#
# IDEMPOTENT:
#   Bucket allaqachon mavjud bo'lsa — xato chiqmaydi (mb --ignore-existing).
#
# BUCKET NOMI VA CONFIG UYG'UNLIGI:
#   backend/app/core/config.py dagi MINIO_BUCKET_* sozlamalari bilan mos:
#     minio_bucket_products  = retail-products
#     minio_bucket_contracts = retail-contracts
#     minio_bucket_proofs    = retail-delivery-proofs
#     minio_bucket_promo     = retail-promo   (kelajak — config ga qo'shilsa)
# =============================================================================

set -euo pipefail

# ─── O'zgaruvchilar ──────────────────────────────────────────────────────────

MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://minio:9000}"
MINIO_ROOT_USER="${MINIO_ROOT_USER:-}"
MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-}"

# mc alias nomi (har ishga tushishda vaqtincha)
MC_ALIAS="retail_minio_$$"

# Yaratilishi kerak bo'lgan bucketlar
BUCKETS=(
    "retail-products"           # Mahsulot rasmlari
    "retail-contracts"          # Shartnoma fayllari
    "retail-delivery-proofs"    # Yetkazish tasdiqlash rasmlar
    "retail-promo"              # Promo/aksiya materiallar
)

# ─── Ranglar ─────────────────────────────────────────────────────────────────

_RED='\033[0;31m'
_GRN='\033[0;32m'
_YLW='\033[1;33m'
_RST='\033[0m'

info()  { echo -e "${_GRN}[INFO]${_RST}  $*"; }
warn()  { echo -e "${_YLW}[WARN]${_RST}  $*"; }
error() { echo -e "${_RED}[ERROR]${_RST} $*" >&2; }
die()   { error "$*"; exit 1; }

# ─── Tekshiruvlar ─────────────────────────────────────────────────────────────

if [[ -z "$MINIO_ROOT_USER" ]]; then
    die "MINIO_ROOT_USER o'rnatilmagan.\n  export MINIO_ROOT_USER='<access_key>'"
fi

if [[ -z "$MINIO_ROOT_PASSWORD" ]]; then
    die "MINIO_ROOT_PASSWORD o'rnatilmagan.\n  export MINIO_ROOT_PASSWORD='<secret_key>'"
fi

if ! command -v mc &>/dev/null; then
    die "mc (MinIO Client) topilmadi.\n  https://min.io/docs/minio/linux/reference/minio-mc.html\n  wget https://dl.min.io/client/mc/release/linux-amd64/mc && chmod +x mc && mv mc /usr/local/bin/"
fi

# ─── MinIO ga ulanish ─────────────────────────────────────────────────────────

info "MinIO ga ulanilmoqda: $MINIO_ENDPOINT"

# Trap: chiqishda aliasni tozalash
cleanup() {
    mc alias remove "$MC_ALIAS" &>/dev/null || true
}
trap cleanup EXIT

mc alias set "$MC_ALIAS" "$MINIO_ENDPOINT" "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" --api s3v4 &>/dev/null
info "MinIO ulanish muvaffaqiyatli: alias=$MC_ALIAS"

# ─── MinIO tayyorligini kutish ────────────────────────────────────────────────

MAX_WAIT=60
WAITED=0
info "MinIO tayyorligini tekshirilmoqda..."
until mc admin info "$MC_ALIAS" &>/dev/null; do
    if [[ $WAITED -ge $MAX_WAIT ]]; then
        die "MinIO $MAX_WAIT sekund ichida ishga tushmadi. Endpoint: $MINIO_ENDPOINT"
    fi
    info "MinIO hali tayyor emas — 3 sekund kutilmoqda ($WAITED/$MAX_WAIT)..."
    sleep 3
    WAITED=$((WAITED + 3))
done
info "MinIO tayyor."

# ─── Bucket'larni yaratish ────────────────────────────────────────────────────

info "Bucket'lar yaratilmoqda..."

for bucket in "${BUCKETS[@]}"; do
    if mc ls "$MC_ALIAS/$bucket" &>/dev/null; then
        info "  $bucket — allaqachon mavjud, o'tkazib yuborildi."
    else
        mc mb "$MC_ALIAS/$bucket" --ignore-existing
        info "  $bucket — YANGI yaratildi."
    fi
done

# ─── Versioning (ixtiyoriy, tavsiya etiladi) ──────────────────────────────────

# Mahsulot rasmlari va shartnomalar uchun versioning yoqish
# (Accidental delete ni kamaytirish uchun)
for bucket in "retail-products" "retail-contracts"; do
    if mc version info "$MC_ALIAS/$bucket" 2>/dev/null | grep -q "enabled"; then
        info "  $bucket versioning — allaqachon yoqilgan."
    else
        mc version enable "$MC_ALIAS/$bucket" &>/dev/null \
            && info "  $bucket versioning — yoqildi." \
            || warn "  $bucket versioning yoqishda xato — qo'lda yoqing."
    fi
done

# ─── Bucket'lar ro'yxati (tasdiqlash) ────────────────────────────────────────

echo ""
info "=== Mavjud bucket'lar ro'yxati ==="
mc ls "$MC_ALIAS/"
echo ""

info "=== MinIO bucket yaratish yakunlandi ==="
echo ""
echo "  Endpoint : $MINIO_ENDPOINT"
echo "  Bucket'lar:"
for bucket in "${BUCKETS[@]}"; do
    echo "    - $bucket"
done
echo ""
warn "Eslatma: bucket nomlar backend/app/core/config.py dagi MINIO_BUCKET_* sozlamalari bilan mos bo'lishi shart."
