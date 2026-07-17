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
# solo server MCP (Postgres resta su) -> pg_restore su un DB TEMPORANEO ->
# validazione -> swap per rinomina (terminate connessioni) -> drop del vecchio.
# Al termine riavvia il server con `mise run start-hindsight` (o riapri una
# sessione Claude Code).
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

# Filtro rapido: -Fc valida l'header, quindi un file palesemente rotto muore qui
# senza toccare niente. NON e' una difesa: --list legge solo il TOC (in testa al
# file), quindi un dump TRONCATO passa (verificato: troncato al 50/90/99% -> exit 0
# e restore poi fallito a meta'). Da quello protegge il restore su DB temporaneo.
if ! "$PG_RESTORE" --list "$DUMP" > /dev/null 2>&1; then
	echo "[db-restore] RIFIUTATO: dump illeggibile o corrotto — DB locale non toccato" >&2
	exit 1
fi

# Prerequisito: Postgres raggiungibile. Senza questa probe hs_db_exists non
# distingue "DB assente" (primo restore) da "server muto" (Postgres che sta
# ancora partendo): si classificherebbe 'primo restore' — niente guardrail ne'
# dump di sicurezza — e se il server diventasse raggiungibile a meta' corsa si
# arriverebbe allo swap del DB reale senza alcuna protezione.
if ! hs_db_ping; then
	echo "[db-restore] RIFIUTATO: Postgres non risponde su $PGHOST:$PGPORT." >&2
	echo "               Avvia il cluster (mise run start-hindsight) e riprova." >&2
	exit 1
fi

# Il watermark locale governa TRE decisioni: guardrail sul sidecar, confronto col
# dump e dump di sicurezza. Un vuoto AMBIGUO le spegne tutte e porta dritto al DROP,
# quindi va distinto: DB assente = primo restore, niente da perdere. DB presente ma
# muto = non sappiamo cosa stiamo per distruggere -> ci si ferma.
LOCAL_WM=""
if hs_db_exists; then
	if ! LOCAL_WM="$(hs_db_watermark)"; then
		if [ "$FORCE" -ne 1 ]; then
			echo "[db-restore] RIFIUTATO: '$PGDATABASE' esiste ma non riesco a leggerne il watermark." >&2
			echo "               Non so cosa contiene: non posso ne' confrontarlo col dump ne' salvarlo." >&2
			echo "               Se sai cosa stai facendo, rilancia con --force." >&2
			exit 2
		fi
		echo "[db-restore] --force: procedo senza aver letto il watermark locale" >&2
		LOCAL_WM=""
	fi
else
	echo "[db-restore] database '$PGDATABASE' assente: primo restore su questa macchina"
fi

# Sidecar assente/illeggibile: senza il watermark del dump il confronto sotto non
# puo' scattare e si arriverebbe al DROP in silenzio, col solo warning stampato
# sopra. Se il DB locale ha qualcosa da perdere, fermati: decide l'operatore.
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

# --- 4. Restore su un DB TEMPORANEO ------------------------------------------
# Il DB corrente non si tocca finche' il restore non e' riuscito: prima si faceva
# DROP + CREATE e solo dopo pg_restore, quindi un dump troncato (che supera --list,
# vedi sopra) lasciava un DB parziale da recuperare a mano dal dump di sicurezza.
TS="$(date -u +%Y%m%d%H%M%S)"
NEWDB="${PGDATABASE}_new_$TS"
OLDDB="${PGDATABASE}_old_$TS"

# WITH (FORCE): termina da solo eventuali connessioni residue al DB temporaneo
# (es. il pg_restore appena interrotto), che altrimenti bloccherebbero il drop.
drop_newdb() { "$PSQL" "${PGARGS[@]}" -d postgres -qc "DROP DATABASE IF EXISTS \"$NEWDB\" WITH (FORCE);" > /dev/null 2>&1 || true; }

# Cleanup su uscita anomala (Ctrl-C, kill, errore): senza trap un kill durante
# pg_restore (minuti) lascia '$NEWDB' orfano (~330MB, run dopo run); un kill tra
# le due rinomine dello swap lascia il DB SOLO col nome '$OLDDB', senza nessun
# '$PGDATABASE' e senza messaggi. PHASE dice alla trap cosa c'e' da pulire.
PHASE=""
cleanup() {
	rc=$?
	case "$PHASE" in
	restore)
		echo "[db-restore] uscita anomala: rimuovo il DB temporaneo '$NEWDB'" >&2
		drop_newdb
		;;
	swap)
		if "$PSQL" "${PGARGS[@]}" -d postgres -qc "ALTER DATABASE \"$OLDDB\" RENAME TO \"$PGDATABASE\";" > /dev/null 2>&1; then
			echo "[db-restore] uscita durante lo swap: '$PGDATABASE' ripristinato (era '$OLDDB')" >&2
		else
			echo "[db-restore] ATTENZIONE: il DB originale e' rimasto col nome '$OLDDB' — rinominalo a mano in '$PGDATABASE'" >&2
		fi
		drop_newdb
		;;
	esac
	exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "[db-restore] restore su '$NEWDB' ('$PGDATABASE' resta intatto)"
PHASE="restore"
"$PSQL" "${PGARGS[@]}" -d postgres -qc "CREATE DATABASE \"$NEWDB\" OWNER \"$PGUSER\";" || {
	echo "[db-restore] ERRORE: create del DB temporaneo fallito" >&2
	exit 1
}
if ! "$PG_RESTORE" "${PGARGS[@]}" -d "$NEWDB" --no-owner "$DUMP"; then
	echo "[db-restore] ERRORE: pg_restore ha riportato errori — '$PGDATABASE' NON e' stato toccato" >&2
	exit 1 # la trap rimuove il DB temporaneo
fi
# Validazione prima dello swap: lo schema ripristinato e' leggibile? Intercetta i
# dump che pg_restore accetta ma che non producono un DB utilizzabile.
if ! NEW_WM="$(hs_db_watermark "$NEWDB")"; then
	echo "[db-restore] ERRORE: il DB ripristinato non e' leggibile — '$PGDATABASE' NON e' stato toccato" >&2
	exit 1 # la trap rimuove il DB temporaneo
fi

# --- 5. Swap per rinomina -----------------------------------------------------
# L'originale non viene MAI droppato prima che il nuovo sia al suo posto: cambia
# solo nome. Tra le due rinomine resta un breve istante in cui '$PGDATABASE' non
# esiste (ALTER DATABASE RENAME non e' transazionabile): se qualcosa muore li',
# la trap (PHASE=swap) rimette il nome originale.
"$PSQL" "${PGARGS[@]}" -d postgres -qc \
	"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname IN ('$PGDATABASE','$NEWDB') AND pid<>pg_backend_pid();" > /dev/null 2>&1 || true

RENAMED=0
if hs_db_exists; then
	"$PSQL" "${PGARGS[@]}" -d postgres -qc "ALTER DATABASE \"$PGDATABASE\" RENAME TO \"$OLDDB\";" || {
		echo "[db-restore] ERRORE: impossibile mettere da parte '$PGDATABASE' (connessioni attive?) — nulla e' cambiato" >&2
		exit 1 # la trap rimuove il DB temporaneo
	}
	RENAMED=1
	PHASE="swap"
fi
if ! "$PSQL" "${PGARGS[@]}" -d postgres -qc "ALTER DATABASE \"$NEWDB\" RENAME TO \"$PGDATABASE\";"; then
	echo "[db-restore] ERRORE: swap fallito" >&2
	exit 1 # la trap rimette '$OLDDB' come '$PGDATABASE' (o dice come farlo a mano) e rimuove '$NEWDB'
fi
PHASE=""
# Swap riuscito: il vecchio non serve piu' (il rollback resta nel dump di sicurezza).
if [ "$RENAMED" -eq 1 ] && ! "$PSQL" "${PGARGS[@]}" -d postgres -qc "DROP DATABASE IF EXISTS \"$OLDDB\";" > /dev/null 2>&1; then
	echo "[db-restore] ATTENZIONE: drop di '$OLDDB' fallito (connessioni?) — rimuovilo a mano, occupa spazio" >&2
fi

echo "[db-restore] OK — watermark del DB ripristinato: $NEW_WM"
echo "[db-restore] riavvia il server: mise run start-hindsight (o riapri Claude Code)"
exit 0
