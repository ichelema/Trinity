# Sourced da hs-db-dump.sh / hs-db-restore.sh: risolve i binari Postgres del
# cluster pg0 e i parametri di connessione, per-OS. Nessun path hardcoded:
# tutto sovrascrivibile via env (HS_PG*, HS_BACKUP_DIR).
#
# Il cluster pg0 vive nel profilo dell'utente:
#   Windows: %HOMEDRIVE%%HOMEPATH%/.pg0  (USERPROFILE e' redirezionato alla
#            chiavetta e pg0 usa il profilo REALE via platformdirs)
#   Linux:   $HOME/.pg0

case "$(uname -s)" in
MINGW* | MSYS* | CYGWIN*)
	_HS_OS=windows
	_PG_HOME_U="$(cygpath -u "$HOMEDRIVE$HOMEPATH")"
	PGBIN="${HS_PGBIN:-$(ls -d "$_PG_HOME_U"/.pg0/installation/*/bin 2>/dev/null | sort -V | tail -1)}"
	_EXE=".exe"
	# Default: i dump viaggiano sulla chiavetta (fa da corriere tra le macchine).
	BACKUP_DIR="${HS_BACKUP_DIR:-E:/var/backups/hindsight}"
	;;
*)
	_HS_OS=linux
	PGBIN="${HS_PGBIN:-$(ls -d "$HOME"/.pg0/installation/*/bin 2>/dev/null | sort -V | tail -1)}"
	_EXE=""
	BACKUP_DIR="${HS_BACKUP_DIR:-$HOME/backups/hindsight}"
	;;
esac

PG_DUMP="$PGBIN/pg_dump$_EXE"
PG_RESTORE="$PGBIN/pg_restore$_EXE"
PSQL="$PGBIN/psql$_EXE"

# Credenziali dell'istanza pg0 "hindsight-mcp" (fisse nel suo instance.json).
export PGPASSWORD="${HS_PGPASSWORD:-hindsight}"
PGHOST="${HS_PGHOST:-127.0.0.1}"
PGPORT="${HS_PGPORT:-5432}"
PGUSER="${HS_PGUSER:-hindsight}"
PGDATABASE="${HS_PGDATABASE:-hindsight}"

# Argomenti di connessione comuni (array: path/valori con spazi sicuri).
PGARGS=(-h "$PGHOST" -p "$PGPORT" -U "$PGUSER")

hs_db_require_pgbin() {
	if [ ! -x "$PSQL" ]; then
		echo "[hs-db] binari Postgres pg0 non trovati (PGBIN='$PGBIN'). Cluster mai inizializzato? Override: HS_PGBIN." >&2
		exit 1
	fi
}

# Ultima scrittura nel DB (watermark anti-perdita): max created_at tra documents
# (il retain scrive qui subito) e memory_units (estrazione async). Stampa ISO o
# stringa vuota se il DB e' vuoto/irraggiungibile.
hs_db_watermark() {
	local db="${1:-$PGDATABASE}"
	"$PSQL" "${PGARGS[@]}" -d "$db" -tA -c \
		"SELECT COALESCE(GREATEST((SELECT max(created_at) FROM documents), (SELECT max(created_at) FROM memory_units))::text, '')" \
		2>/dev/null | tr -d '\r'
}

hs_db_host_label() {
	printf '%s' "${COMPUTERNAME:-$(hostname 2>/dev/null || echo host-sconosciuto)}"
}
