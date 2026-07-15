#!/usr/bin/env bash
# Restore del database Hindsight da un dump di hs-db-dump.sh, con GUARDRAIL
# anti-perdita: se il DB locale contiene scritture PIU' RECENTI del dump,
# rifiuta (il restore e' una fotografia integrale: sovrascriverebbe quelle
# memorie). --force per procedere consapevolmente.
#
# Uso: hs-db-restore.sh [file.dump] [--force]
#   senza argomento usa l'ultimo dump (file LATEST in BACKUP_DIR).
#
# Sequenza: guardrail (sola lettura) -> dump di sicurezza locale -> stop del
# solo server MCP (Postgres resta su) -> terminate connessioni -> drop/create
# -> pg_restore --no-owner. Al termine riavvia il server con
# `mise run start-hindsight` (o riapri una sessione Claude Code).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/hs-db-lib.sh"

hs_db_require_pgbin

DUMP=""
FORCE=0
for arg in "$@"; do
	case "$arg" in
	--force) FORCE=1 ;;
	*) DUMP="$arg" ;;
	esac
done

# Default: l'ultimo dump registrato in LATEST.
if [ -z "$DUMP" ]; then
	if [ ! -f "$BACKUP_DIR/LATEST" ]; then
		echo "[db-restore] nessun dump indicato e nessun LATEST in $BACKUP_DIR" >&2
		exit 1
	fi
	DUMP="$BACKUP_DIR/$(tr -d '\r\n' < "$BACKUP_DIR/LATEST")"
fi
[ -f "$DUMP" ] || {
	echo "[db-restore] dump non trovato: $DUMP" >&2
	exit 1
}

# --- 1. GUARDRAIL (sola lettura, prima di qualsiasi azione) ------------------
DUMP_WM=""
if [ -f "$DUMP.meta.json" ]; then
	DUMP_WM="$(grep -o '"max_write_at": *"[^"]*"' "$DUMP.meta.json" | cut -d'"' -f4)"
	if [ -z "$DUMP_WM" ]; then
		# Sidecar scritto prima che il watermark includesse updated_at (campo
		# 'max_created_at'). Senza questo fallback DUMP_WM resterebbe vuoto e il
		# guardrail sotto NON scatterebbe: si arriverebbe al DROP senza confronto.
		# Il valore vecchio sottostima le scritture del dump -> il confronto e'
		# conservativo (semmai rifiuta di piu', mai di meno).
		DUMP_WM="$(grep -o '"max_created_at": *"[^"]*"' "$DUMP.meta.json" | cut -d'"' -f4)"
		[ -n "$DUMP_WM" ] && echo "[db-restore] dump con watermark vecchio (solo created_at): confronto conservativo" >&2
	fi
	DUMP_HOST="$(grep -o '"host": *"[^"]*"' "$DUMP.meta.json" | cut -d'"' -f4)"
	echo "[db-restore] dump: $(basename "$DUMP") (host: ${DUMP_HOST:-?}, watermark: ${DUMP_WM:-?})"
else
	echo "[db-restore] ATTENZIONE: $DUMP.meta.json assente — guardrail non applicabile" >&2
fi

LOCAL_WM="$(hs_db_watermark)"
# Sidecar assente/illeggibile: senza il watermark del dump il confronto sotto non
# puo' scattare e si arriverebbe al DROP in silenzio, col solo warning stampato
# sopra. Se il DB locale ha qualcosa da perdere, fermati: decide l'operatore.
# LOCAL_WM vuoto (DB vuoto o irraggiungibile) NON e' un caso da bloccare: non c'e'
# nulla da sovrascrivere ed e' il primo restore su una macchina nuova.
if [ -n "$LOCAL_WM" ] && [ -z "$DUMP_WM" ] && [ "$FORCE" -ne 1 ]; then
	echo "[db-restore] RIFIUTATO: watermark del dump non disponibile (sidecar assente o illeggibile)." >&2
	echo "               Non posso stabilire se il dump e' piu' vecchio del DB locale." >&2
	echo "               locale: $LOCAL_WM" >&2
	echo "               Se sai cosa stai facendo, rilancia con --force." >&2
	exit 2
fi
if [ -n "$LOCAL_WM" ] && [ -n "$DUMP_WM" ]; then
	# Confronto lessicografico: i timestamp ISO (stesso fuso +00) ordinano bene.
	if [[ "$LOCAL_WM" > "$DUMP_WM" ]] && [ "$FORCE" -ne 1 ]; then
		echo "[db-restore] RIFIUTATO: il DB locale ha scritture piu' recenti del dump." >&2
		echo "               locale: $LOCAL_WM" >&2
		echo "               dump:   $DUMP_WM" >&2
		echo "               Se procedi, le memorie locali successive al dump vanno perse." >&2
		echo "               Prima fai 'mise run db-dump' qui, oppure rilancia con --force." >&2
		exit 2
	fi
	[ "$FORCE" -eq 1 ] && [[ "$LOCAL_WM" > "$DUMP_WM" ]] && echo "[db-restore] --force: sovrascrivo scritture locali piu' recenti ($LOCAL_WM > $DUMP_WM)"
fi

# --- 2. Dump di sicurezza del DB locale (se raggiungibile e non vuoto) -------
if [ -n "$LOCAL_WM" ]; then
	SAFE="$BACKUP_DIR/pre-restore-$(hs_db_host_label)-$(date -u +%Y%m%dT%H%M%SZ).dump"
	mkdir -p "$BACKUP_DIR"
	echo "[db-restore] dump di sicurezza del DB locale -> $(basename "$SAFE")"
	"$PG_DUMP" "${PGARGS[@]}" -d "$PGDATABASE" -Fc -f "$SAFE" || {
		echo "[db-restore] ERRORE: dump di sicurezza fallito — mi fermo (il DB locale resta intatto)" >&2
		exit 1
	}
fi

# --- 3. Ferma il SOLO server MCP (Postgres deve restare su) ------------------
# Serve solo se il target e' il DB a cui il server e' connesso ('hindsight'):
# con un target diverso (es. test) il server puo' restare su.
if [ "$PGDATABASE" = "hindsight" ]; then
	case "$_HS_OS" in
	windows) /c/Windows/System32/taskkill.exe //F //T //IM hindsight-local-mcp.exe > /dev/null 2>&1 || true ;;
	*) pkill -TERM -f hindsight-local-mcp > /dev/null 2>&1 || true ;;
	esac
	sleep 1
fi

# --- 4. Chiudi le connessioni residue e ricrea il database -------------------
"$PSQL" "${PGARGS[@]}" -d postgres -qc \
	"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$PGDATABASE' AND pid<>pg_backend_pid();" > /dev/null 2>&1 || true

echo "[db-restore] drop + create di '$PGDATABASE'"
"$PSQL" "${PGARGS[@]}" -d postgres -qc "DROP DATABASE IF EXISTS \"$PGDATABASE\";" || {
	echo "[db-restore] ERRORE: drop fallito (connessioni attive?)" >&2
	exit 1
}
"$PSQL" "${PGARGS[@]}" -d postgres -qc "CREATE DATABASE \"$PGDATABASE\" OWNER \"$PGUSER\";" || {
	echo "[db-restore] ERRORE: create fallito" >&2
	exit 1
}

# --- 5. Restore ---------------------------------------------------------------
echo "[db-restore] pg_restore in corso..."
if ! "$PG_RESTORE" "${PGARGS[@]}" -d "$PGDATABASE" --no-owner "$DUMP"; then
	echo "[db-restore] ERRORE: pg_restore ha riportato errori — controlla l'output sopra" >&2
	exit 1
fi

NEW_WM="$(hs_db_watermark)"
echo "[db-restore] OK — watermark del DB ripristinato: $NEW_WM"
echo "[db-restore] riavvia il server: mise run start-hindsight (o riapri Claude Code)"
exit 0
