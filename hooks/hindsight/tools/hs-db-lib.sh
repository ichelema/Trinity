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

# Ultima scrittura nel DB (watermark anti-perdita): l'istante piu' recente tra
# documents (il retain scrive qui subito) e memory_units (estrazione async).
# Stampa ISO, oppure stringa vuota se il DB non ha scritture. ESITO NELL'EXIT CODE:
# 0 = psql ha risposto (il valore stampato e' attendibile, anche se vuoto)
# 1 = psql e' muto (server giu', credenziali, DB inesistente): valore IGNOTO.
# La distinzione e' obbligatoria: nel restore un watermark vuoto disattiva sia il
# guardrail sia il dump di sicurezza, quindi "non so cosa c'e'" trattato come "non
# c'e' niente da perdere" porta dritto al DROP di un DB pieno.
#
# created_at NON basta: il retain usa un document_id stabile per sessione (vedi
# compute_document_id nel worker), quindi ogni Stop successivo AGGIORNA lo stesso
# documento invece di inserirne uno nuovo; la consolidation fa lo stesso sulle
# observation (fonde, non inserisce). Sul DB reale meta' dei documents e un quarto
# delle memory_units hanno updated_at > created_at, con gap fino a 25 giorni: con
# solo created_at il watermark resterebbe fermo al giorno della PRIMA scrittura e
# il guardrail accetterebbe un dump piu' vecchio del lavoro appena fatto.
hs_db_watermark() {
	local db="${1:-$PGDATABASE}" out
	# Query di CATALOGO: gira su qualunque DB raggiungibile, anche senza le tabelle
	# applicative. Se fallisce, psql e' muto -> esito ignoto. NB: il vecchio codice
	# aveva il pipe a `tr` DENTRO la sostituzione, quindi leggeva l'exit di tr (0
	# sempre) e non quello di psql: da qui il vuoto ambiguo.
	out="$("$PSQL" "${PGARGS[@]}" -d "$db" -tAc \
		"SELECT count(*) FROM pg_class WHERE relname IN ('documents','memory_units') AND relkind='r'" 2>/dev/null)" || return 1
	# Tabelle assenti = DB nuovo, mai migrato. Esito NOTO: nessuna scrittura.
	[ "$(printf '%s' "$out" | tr -dc '0-9')" = "2" ] || return 0
	out="$("$PSQL" "${PGARGS[@]}" -d "$db" -tAc \
		"SELECT COALESCE(GREATEST((SELECT max(GREATEST(created_at, updated_at)) FROM documents), (SELECT max(GREATEST(created_at, updated_at)) FROM memory_units))::text, '')" 2>/dev/null)" || return 1
	printf '%s' "$out" | tr -d '\r'
}

# 0 se il server Postgres risponde. Da chiamare PRIMA di fidarsi di hs_db_exists:
# il suo exit 1 significa "DB assente" solo a server raggiungibile — senza questa
# probe "server muto" (es. Postgres sta ancora partendo) e "DB assente" sono
# indistinguibili, e il restore classificherebbe 'primo restore' un DB che c'e'.
hs_db_ping() {
	"$PSQL" "${PGARGS[@]}" -d postgres -qtAc "SELECT 1" > /dev/null 2>&1
}

# 0 se il database esiste. Distingue "DB assente" (primo restore: niente da perdere)
# da "DB presente ma illeggibile" (fermarsi), che hs_db_watermark da solo non separa.
hs_db_exists() {
	local db="${1:-$PGDATABASE}" out
	out="$("$PSQL" "${PGARGS[@]}" -d postgres -tAc \
		"SELECT 1 FROM pg_database WHERE datname='$db'" 2>/dev/null)" || return 1
	[ -n "$(printf '%s' "$out" | tr -dc '0-9')" ]
}

hs_db_host_label() {
	printf '%s' "${COMPUTERNAME:-$(hostname 2>/dev/null || echo host-sconosciuto)}"
}
