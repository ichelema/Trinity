#!/usr/bin/env bash
#
# cp-redirect-test.sh <versione> [porta]
#
# Avvia il Control Plane Hindsight della <versione> indicata su una porta
# usa-e-getta (default 9998, NON 9999 → non tocca l'istanza in produzione) e
# verifica come si comporta "/":
#   - 0.7.0 (rotto):  / → 307 → / → 307 → …  loop infinito (ERR_TOO_MANY_REDIRECTS)
#   - 0.6.2 (ok):     / → 307 → /dashboard → 200
#
# curl segue i redirect con un tetto (--max-redirs 10): il loop lo esaurisce e
# curl esce con codice 47 → è il nostro segnale di "ancora rotto".
#
# Exit:  0 = OK (/ porta a /dashboard, 200)
#        1 = ANCORA ROTTO (loop di redirect)
#        2 = il server non si è avviato
#        3 = comportamento inatteso, guarda a mano

set -uo pipefail

VERSION="${1:?uso: cp-redirect-test.sh <versione> [porta]}"
PORT="${2:-9998}"
PKG="@vectorize-io/hindsight-control-plane"
API_URL="http://localhost:8888"
LOG="/tmp/cp-test-${PORT}.log"
ERRF="/tmp/cp-test-${PORT}.err"

echo "=== Test redirect ${PKG}@${VERSION} su 127.0.0.1:${PORT} ==="

# Avvio in background. PORT (env) anziché --port: Next.js standalone la rispetta
# in modo affidabile su tutte le versioni. npx risolve al Node mise (vedi [tools]).
PORT="${PORT}" HOSTNAME=127.0.0.1 \
	npx --yes "${PKG}@${VERSION}" --hostname 127.0.0.1 --api-url "${API_URL}" \
	>"${LOG}" 2>&1 &
CP_PID=$!

cleanup() {
	kill "${CP_PID}" 2>/dev/null
	# kill-port: il netstat MSYS non vede sempre i processi Node nativi → usa Get-NetTCPConnection
	# kill-port.sh vive in hooks/hindsight/ops/ di questo stesso repo; TRINITY_PLUGIN_DIR
	# se presente (env utente), fallback alla root del repo: scheduler/check_update_*/ -> ../..
	bash "${TRINITY_PLUGIN_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}/hooks/hindsight/ops/kill-port.sh" "${PORT}" cp-test >/dev/null 2>&1
	rm -f "${ERRF}"
}
trap cleanup EXIT

# Attendo che il server risponda (max ~45s: il primo avvio scarica il pacchetto via npx)
up=0
for _ in $(seq 1 45); do
	code=$(curl -sS -o /dev/null -w "%{http_code}" -m 2 "http://127.0.0.1:${PORT}/api/health" 2>/dev/null || true)
	if [[ "${code}" =~ ^(200|204|404)$ ]]; then
		up=1
		break
	fi
	sleep 1
done

if [[ "${up}" -ne 1 ]]; then
	echo "VERDETTO: AVVIO FALLITO — nessuna risposta su :${PORT} dopo 45s."
	echo "--- ultime righe di ${LOG} ---"
	tail -n 25 "${LOG}" 2>/dev/null
	exit 2
fi

# Seguo "/" con tetto ai redirect; catturo codice finale e URL di approdo.
out=$(curl -sS -L --max-redirs 10 -o /dev/null \
	-w "%{http_code} %{url_effective}" "http://127.0.0.1:${PORT}/" 2>"${ERRF}")
rc=$?
err=$(cat "${ERRF}" 2>/dev/null)

if [[ ${rc} -eq 47 ]] || grep -qi "maximum.*redirect" <<<"${err}"; then
	echo "VERDETTO: ANCORA ROTTO — loop di redirect su / (${err:-curl exit 47})."
	echo "          La ${VERSION} ha ancora il bug i18n della 0.7.0: tieni il pin com'è."
	exit 1
fi

http_code="${out%% *}"
final_url="${out#* }"

if [[ "${http_code}" == "200" && "${final_url}" == *"/dashboard"* ]]; then
	echo "VERDETTO: OK ✅ — / → ${final_url} (${http_code})."
	echo "          La ${VERSION} sembra a posto: puoi aggiornare il pin nel task control-plane."
	exit 0
fi

echo "VERDETTO: DA VERIFICARE A MANO — / → ${final_url} (${http_code}), curl rc=${rc}."
exit 3
