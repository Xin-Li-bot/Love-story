#!/bin/sh
set -eu

umask 077

DATA_DIR="${DATA_DIR:-/var/lib/love-story}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/love-story}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DESTINATION="$BACKUP_DIR/$STAMP"

case "$BACKUP_DIR" in
    ""|/|/var|/var/backups)
        echo "Refusing unsafe BACKUP_DIR: $BACKUP_DIR" >&2
        exit 2
        ;;
esac

case "$RETENTION_DAYS" in
    *[!0-9]*|"")
        echo "RETENTION_DAYS must be a positive integer" >&2
        exit 2
        ;;
esac

if [ "$RETENTION_DAYS" -eq 0 ]; then
    echo "RETENTION_DAYS must be greater than zero" >&2
    exit 2
fi

command -v sqlite3 >/dev/null 2>&1 || {
    echo "sqlite3 is required for an online-consistent database backup" >&2
    exit 1
}

mkdir -p "$DESTINATION"
cleanup_incomplete() {
    if [ ! -f "$DESTINATION/COMPLETE" ]; then
        rm -rf -- "$DESTINATION"
    fi
}
trap cleanup_incomplete EXIT
trap 'exit 1' HUP INT TERM

if [ -f "$DATA_DIR/database.db" ]; then
    sqlite3 "$DATA_DIR/database.db" ".timeout 10000" ".backup '$DESTINATION/database.db'"
fi

if [ -f "$DATA_DIR/timeline.json" ]; then
    cp -p "$DATA_DIR/timeline.json" "$DESTINATION/timeline.json"
fi

if [ -d "$DATA_DIR/photos" ]; then
    tar -C "$DATA_DIR" -czf "$DESTINATION/photos.tar.gz" photos
fi

{
    echo "created_utc=$STAMP"
    echo "source_data_dir=$DATA_DIR"
    echo "hostname=$(hostname)"
} > "$DESTINATION/metadata.txt"

(
    cd "$DESTINATION"
    sha256sum ./* > SHA256SUMS
)

touch "$DESTINATION/COMPLETE"
find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -mtime "+$RETENTION_DAYS" -exec rm -rf -- {} +

echo "Backup complete: $DESTINATION"
