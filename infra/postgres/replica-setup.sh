#!/usr/bin/env bash
# =============================================================================
# infra/postgres/replica-setup.sh
# PostgreSQL Streaming Replication sozlash skripti
# Primary → Replica (hot standby)
#
# FOYDALANISH:
#   Primary serverda:
#     bash infra/postgres/replica-setup.sh primary
#
#   Replica serverda:
#     REPLICATOR_PASSWORD=<parol> \
#     PRIMARY_HOST=<primary_ip_yoki_hostname> \
#       bash infra/postgres/replica-setup.sh replica
#
# TALABLAR:
#   - PostgreSQL 15+
#   - Primary va replica bir xil major versiyada bo'lishi shart
#   - Replica serverda PostgreSQL o'rnatilgan, lekin klaster ISHLAMAYOTGAN bo'lishi kerak
#   - pg_basebackup utility o'rnatilgan (postgresql-client paketi)
#   - REPLICATOR_PASSWORD muhit o'zgaruvchisi o'rnatilgan
#
# DIQQAT:
#   - Bu skript produktsiya tizimiga ta'sir qiladi.
#   - Ishga tushirishdan avval docs/DEPLOY.md ni to'liq o'qing.
#   - Barcha buyruqlarni root yoki postgres foydalanuvchisi sifatida bajaring.
# =============================================================================

set -euo pipefail

# ─── O'zgaruvchilar ──────────────────────────────────────────────────────────

# Replication foydalanuvchisi nomi
REPLICATOR_USER="${REPLICATOR_USER:-replicator}"

# Replication foydalanuvchisi paroli — muhit o'zgaruvchisidan (MAJBURIY)
REPLICATOR_PASSWORD="${REPLICATOR_PASSWORD:-}"

# Primary server manzili (replica uchun)
PRIMARY_HOST="${PRIMARY_HOST:-postgres-primary}"
PRIMARY_PORT="${PRIMARY_PORT:-5432}"

# PostgreSQL ma'lumotlar papkasi
PGDATA="${PGDATA:-/var/lib/postgresql/data}"

# PostgreSQL sozlamalar fayllari joylashuvi
PGCONF="${PGCONF:-${PGDATA}/postgresql.conf}"
PG_HBA="${PG_HBA:-${PGDATA}/pg_hba.conf}"

# Replica IP (primary pg_hba.conf uchun; bo'sh bo'lsa — /32 subnet ishlatilmaydi)
REPLICA_IP="${REPLICA_IP:-}"

# ─── Ranglar ─────────────────────────────────────────────────────────────────

_RED='\033[0;31m'
_YLW='\033[1;33m'
_GRN='\033[0;32m'
_RST='\033[0m'

info()  { echo -e "${_GRN}[INFO]${_RST}  $*"; }
warn()  { echo -e "${_YLW}[WARN]${_RST}  $*"; }
error() { echo -e "${_RED}[ERROR]${_RST} $*" >&2; }
die()   { error "$*"; exit 1; }

# ─── Tekshiruvlar ─────────────────────────────────────────────────────────────

check_root_or_postgres() {
    local user
    user="$(whoami)"
    if [[ "$user" != "root" && "$user" != "postgres" ]]; then
        warn "Bu skript 'root' yoki 'postgres' sifatida ishga tushirilishi kerak."
        warn "Joriy foydalanuvchi: $user"
    fi
}

check_pg_commands() {
    for cmd in psql pg_basebackup; do
        if ! command -v "$cmd" &>/dev/null; then
            die "$cmd topilmadi. postgresql-client paketini o'rnating."
        fi
    done
}

# ─── Primary sozlash ──────────────────────────────────────────────────────────

setup_primary() {
    info "=== PRIMARY sozlash boshlandi ==="
    check_pg_commands

    if [[ -z "$REPLICATOR_PASSWORD" ]]; then
        die "REPLICATOR_PASSWORD muhit o'zgaruvchisi o'rnatilmagan.\n  export REPLICATOR_PASSWORD='<kuchli_parol>'"
    fi

    # 1. Replication foydalanuvchi yaratish (mavjud bo'lsa — yangilash)
    info "1/4. Replication foydalanuvchisi yaratilmoqda: $REPLICATOR_USER"
    psql -U postgres -c "
        DO \$\$
        BEGIN
            IF NOT EXISTS (
                SELECT FROM pg_catalog.pg_roles WHERE rolname = '$REPLICATOR_USER'
            ) THEN
                CREATE ROLE $REPLICATOR_USER REPLICATION LOGIN
                    PASSWORD '$REPLICATOR_PASSWORD';
                RAISE NOTICE 'Role $REPLICATOR_USER yaratildi.';
            ELSE
                ALTER ROLE $REPLICATOR_USER PASSWORD '$REPLICATOR_PASSWORD';
                RAISE NOTICE 'Role $REPLICATOR_USER mavjud — parol yangilandi.';
            END IF;
        END
        \$\$;
    "
    info "Replication foydalanuvchisi tayyor: $REPLICATOR_USER"

    # 2. postgresql.conf sozlamalari
    info "2/4. postgresql.conf — replication sozlamalari tekshirilmoqda"
    if ! grep -q "^wal_level" "$PGCONF" 2>/dev/null; then
        cat >> "$PGCONF" << 'EOF'

# ─── Streaming Replication (replica-setup.sh tomonidan qo'shildi) ─────────────
wal_level = replica
max_wal_senders = 5
max_replication_slots = 5
wal_keep_size = 512MB          # WAL fayllarni ushlab turish hajmi
hot_standby = on               # Replica da read-only so'rovlarga ruxsat
synchronous_commit = on        # Sinxron commit (ma'lumot xavfsizligi uchun)
archive_mode = on
archive_command = 'test ! -f /var/lib/postgresql/archive/%f && cp %p /var/lib/postgresql/archive/%f'
# DIQQAT: archive_command ni sizning zaxira tizimingizga moslashtiring.
EOF
        info "postgresql.conf ga replication sozlamalari qo'shildi."
        warn "PostgreSQL qayta ishga tushirilishi kerak: pg_ctlcluster <version> main restart"
    else
        warn "postgresql.conf da 'wal_level' allaqachon mavjud — qo'lda tekshiring: $PGCONF"
    fi

    # 3. pg_hba.conf — replication ruxsati
    info "3/4. pg_hba.conf — replication ruxsati qo'shilmoqda"
    local hba_comment="# replication (replica-setup.sh)"
    if ! grep -q "$REPLICATOR_USER" "$PG_HBA" 2>/dev/null; then
        if [[ -n "$REPLICA_IP" ]]; then
            echo "$hba_comment"                                     >> "$PG_HBA"
            echo "host replication $REPLICATOR_USER $REPLICA_IP/32 scram-sha-256" >> "$PG_HBA"
            info "pg_hba.conf: $REPLICA_IP/32 uchun replication ruxsati qo'shildi."
        else
            echo "$hba_comment"                                        >> "$PG_HBA"
            echo "host replication $REPLICATOR_USER 0.0.0.0/0 scram-sha-256" >> "$PG_HBA"
            warn "REPLICA_IP o'rnatilmagan — 0.0.0.0/0 ishlatildi."
            warn "Xavfsizlik uchun REPLICA_IP=<replica_ip> qilib qayta ishga tushiring."
        fi
    else
        warn "pg_hba.conf da $REPLICATOR_USER allaqachon mavjud — o'tkazib yuborildi."
    fi

    # 4. Konfiguratsiyani qayta yuklash
    info "4/4. pg_hba.conf qayta yuklanmoqda (pg_reload_conf)"
    psql -U postgres -c "SELECT pg_reload_conf();" >/dev/null

    info "=== PRIMARY sozlash yakunlandi ==="
    echo ""
    warn "KEYINGI QADAMLAR:"
    echo "  1. PostgreSQL qayta ishga tushiring (wal_level o'zgardi):"
    echo "     systemctl restart postgresql"
    echo "     # yoki Docker: docker compose restart postgres-primary"
    echo "  2. Replica serverda bu skriptni ishga tushiring:"
    echo "     PRIMARY_HOST=$PRIMARY_HOST REPLICATOR_PASSWORD=<parol> bash replica-setup.sh replica"
}

# ─── Replica sozlash ──────────────────────────────────────────────────────────

setup_replica() {
    info "=== REPLICA sozlash boshlandi ==="
    check_pg_commands

    if [[ -z "$REPLICATOR_PASSWORD" ]]; then
        die "REPLICATOR_PASSWORD muhit o'zgaruvchisi o'rnatilmagan.\n  export REPLICATOR_PASSWORD='<parol>'"
    fi

    if [[ -z "$PRIMARY_HOST" ]]; then
        die "PRIMARY_HOST o'rnatilmagan.\n  export PRIMARY_HOST=<primary_server_ip>"
    fi

    # 1. Mavjud klasterni to'xtatish va tozalash
    info "1/4. PostgreSQL to'xtatilmoqda va ma'lumotlar papkasi tozalanmoqda"
    warn "DIQQAT: $PGDATA papkasi o'chirilmoqda!"
    warn "Bu operatsiya qaytarib bo'lmaydi. 5 sekund ichida Ctrl+C bilan bekor qilishingiz mumkin."
    sleep 5

    # Xizmatni to'xtatish (Docker yoki systemd)
    if command -v systemctl &>/dev/null; then
        systemctl stop postgresql 2>/dev/null || true
    fi

    # Ma'lumotlar papkasini tozalash
    if [[ -d "$PGDATA" ]]; then
        rm -rf "${PGDATA:?}"/*
        info "$PGDATA tozalandi."
    fi

    # 2. pg_basebackup — primary dan to'liq nusxa olish
    info "2/4. pg_basebackup ishga tushirilmoqda (primary: $PRIMARY_HOST:$PRIMARY_PORT)"
    info "Bu jarayon katta bazalarda uzoq vaqt olishi mumkin..."
    PGPASSWORD="$REPLICATOR_PASSWORD" pg_basebackup \
        -h "$PRIMARY_HOST" \
        -p "$PRIMARY_PORT" \
        -U "$REPLICATOR_USER" \
        -D "$PGDATA" \
        -P \
        -Xs \
        -R \
        --checkpoint=fast
    info "pg_basebackup muvaffaqiyatli yakunlandi."

    # 3. standby.signal faylini tekshirish (pg_basebackup -R bilan avtomatik yaratiladi)
    info "3/4. standby.signal fayli tekshirilmoqda"
    if [[ -f "$PGDATA/standby.signal" ]]; then
        info "standby.signal mavjud — replica rejimi tayyor."
    else
        touch "$PGDATA/standby.signal"
        warn "standby.signal qo'lda yaratildi."
    fi

    # 4. postgresql.auto.conf — primary_conninfo tekshirish
    info "4/4. postgresql.auto.conf — primary_conninfo tekshirilmoqda"
    if grep -q "primary_conninfo" "$PGDATA/postgresql.auto.conf" 2>/dev/null; then
        info "primary_conninfo allaqachon mavjud (pg_basebackup -R tomonidan yozilgan)."
    else
        # Qo'lda yozish (nadir holat)
        cat >> "$PGDATA/postgresql.auto.conf" << EOF
primary_conninfo = 'host=$PRIMARY_HOST port=$PRIMARY_PORT user=$REPLICATOR_USER password=$REPLICATOR_PASSWORD sslmode=prefer'
primary_slot_name = ''
hot_standby = on
EOF
        warn "primary_conninfo qo'lda yozildi — tekshiring: $PGDATA/postgresql.auto.conf"
    fi

    # Fayl huquqlari
    if [[ "$(stat -c '%U' "$PGDATA")" != "postgres" ]]; then
        chown -R postgres:postgres "$PGDATA"
        info "Fayl huquqlari postgres:postgres ga o'zgartirildi."
    fi
    chmod 700 "$PGDATA"

    info "=== REPLICA sozlash yakunlandi ==="
    echo ""
    warn "KEYINGI QADAMLAR:"
    echo "  1. PostgreSQL ishga tushiring:"
    echo "     systemctl start postgresql"
    echo "     # yoki Docker: docker compose start postgres-replica"
    echo "  2. Replication holatini tekshiring (primary da):"
    echo "     psql -U postgres -c \"SELECT * FROM pg_stat_replication;\""
    echo "  3. Replica'da read-only so'rovni tekshiring:"
    echo "     psql -U postgres -c \"SELECT pg_is_in_recovery();\""
    echo "     # 't' qaytishi kerak"
}

# ─── Holat tekshiruvi ─────────────────────────────────────────────────────────

check_replication_status() {
    info "=== Replication holati ==="
    echo ""
    echo "--- Primary: pg_stat_replication ---"
    psql -U postgres -c "
        SELECT
            client_addr,
            state,
            sent_lsn,
            write_lsn,
            flush_lsn,
            replay_lsn,
            (sent_lsn - replay_lsn) AS replication_lag_bytes,
            sync_state
        FROM pg_stat_replication;
    " 2>/dev/null || warn "pg_stat_replication o'qib bo'lmadi (primary da ishga tushirganmisiz?)"

    echo ""
    echo "--- Replica: pg_is_in_recovery ---"
    psql -U postgres -c "SELECT pg_is_in_recovery();" 2>/dev/null \
        || warn "pg_is_in_recovery o'qib bo'lmadi"
}

# ─── Entry point ──────────────────────────────────────────────────────────────

MODE="${1:-help}"

check_root_or_postgres

case "$MODE" in
    primary)
        setup_primary
        ;;
    replica)
        setup_replica
        ;;
    status)
        check_replication_status
        ;;
    help|--help|-h)
        echo "Foydalanish:"
        echo "  bash replica-setup.sh primary   — Primary serverda replication sozlash"
        echo "  bash replica-setup.sh replica   — Replica serverda pg_basebackup va standby sozlash"
        echo "  bash replica-setup.sh status    — Replication holatini tekshirish"
        echo ""
        echo "Muhit o'zgaruvchilari:"
        echo "  REPLICATOR_PASSWORD  — Replication foydalanuvchisi paroli (MAJBURIY)"
        echo "  PRIMARY_HOST         — Primary server manzili (replica uchun; default: postgres-primary)"
        echo "  PRIMARY_PORT         — Primary port (default: 5432)"
        echo "  REPLICA_IP           — Replica IP (primary pg_hba.conf uchun; bo'sh = 0.0.0.0/0)"
        echo "  PGDATA               — PostgreSQL ma'lumotlar papkasi (default: /var/lib/postgresql/data)"
        ;;
    *)
        error "Noto'g'ri argument: $MODE"
        echo "  bash replica-setup.sh {primary|replica|status|help}"
        exit 1
        ;;
esac
