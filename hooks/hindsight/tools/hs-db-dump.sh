#!/usr/bin/env bash
# Dump portabile del database Hindsight (pg_dump -Fc) per il sync tra macchine.
#
# Flusso multi-macchina (uso ALTERNATO, mai concorrente):
#   lasci una macchina  -> mise run db-dump     (il dump finisce in BACKUP_DIR,
#                                                di default sulla chiavetta)
#   arrivi sull'altra   -> mise run db-restore  (guardrail anti-perdita incluso)
#
# Output: <BACKUP_DIR>/hindsight-<UTC>.dump + .meta.json (host, data, watermark)
#         + file LATEST col nome dell'ultimo dump. Tiene le ultime
#         HS_BACKUP_KEEP copie (default 5).
#
# Env: HS_BACKUP_DIR, HS_BACKUP_KEEP, HS_PG* (vedi hs-db-lib.sh)
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/hs-db-lib.sh"

hs_db_require_pgbin
KEEP="${HS_BACKUP_KEEP:-5}"
mkdir -p "$BACKUP_DIR" || {
	echo "[db-dump] impossibile creare $BACKUP_DIR" >&2
	exit 1
}

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$BACKUP_DIR/hindsight-$STAMP.dump"

# Watermark PRIMA del dump: fotografa l'ultima scrittura contenuta nel dump.
WATERMARK="$(hs_db_watermark)"
if [ -z "$WATERMARK" ]; then
	echo "[db-dump] ERRORE: database '$PGDATABASE' irraggiungibile su $PGHOST:$PGPORT (server spento?)" >&2
	exit 1
fi

echo "[db-dump] dump di '$PGDATABASE' -> $OUT"
if ! "$PG_DUMP" "${PGARGS[@]}" -d "$PGDATABASE" -Fc -f "$OUT"; then
	echo "[db-dump] ERRORE: pg_dump fallito" >&2
	rm -f "$OUT"
	exit 1
fi

# Metadata accanto al dump: servono al guardrail del restore.
cat > "$OUT.meta.json" <<EOF
{
  "host": "$(hs_db_host_label)",
  "dumped_at": "$STAMP",
  "max_write_at": "$WATERMARK",
  "database": "$PGDATABASE"
}
EOF
printf '%s\n' "$(basename "$OUT")" > "$BACKUP_DIR/LATEST"

SIZE="$(du -h "$OUT" | cut -f1)"
echo "[db-dump] OK: $SIZE, watermark: $WATERMARK"

# Rotazione: tieni le ultime $KEEP coppie dump+meta (ordinate per nome = per data).
ls -1 "$BACKUP_DIR"/hindsight-*.dump 2>/dev/null | sort | head -n -"$KEEP" | while IFS= read -r old; do
	rm -f "$old" "$old.meta.json"
	echo "[db-dump] rotazione: rimosso $(basename "$old")"
done

exit 0
