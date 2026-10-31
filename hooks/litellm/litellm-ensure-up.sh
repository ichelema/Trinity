#!/usr/bin/env bash
# SessionStart hook — apre il tunnel SSH verso LiteLLM sulla VPS, usato dalla mod
# gpt-bridge su 127.0.0.1:4000. Sui PC LITELLM_SSH_TUNNEL=<host ssh>; sulla VPS la
# variabile non c'e' e LiteLLM risponde gia' in locale.
# La chiave dell'host e' limitata sulla VPS a permitopen="127.0.0.1:4000".
# Esce SEMPRE 0: non deve mai bloccare/fallire la sessione.
set -uo pipefail

# 127.0.0.1 e non localhost: su Windows localhost prova prima IPv6.
URL="http://127.0.0.1:4000/health/liveliness"
DEADLINE_SECS=15

ready() { curl -sf -m 2 -o /dev/null "$URL"; }

ready && exit 0
[ -n "${LITELLM_SSH_TUNNEL:-}" ] || exit 0

# Bind esplicito su 127.0.0.1: con GatewayPorts=yes la porta finirebbe in LAN.
# setsid nohup e non ssh -f: su MSYS il figlio verrebbe reaped all'uscita dell'hook.
setsid nohup ssh -N -o BatchMode=yes -o ExitOnForwardFailure=yes \
    -o ConnectTimeout=10 -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
    -L 127.0.0.1:4000:127.0.0.1:4000 \
    "$LITELLM_SSH_TUNNEL" < /dev/null > /dev/null 2>&1 &
disown 2> /dev/null || true

while [ "$SECONDS" -lt "$DEADLINE_SECS" ]; do
    sleep 1
    ready && exit 0
done

echo "LiteLLM non raggiungibile (tunnel: $LITELLM_SSH_TUNNEL): agenti gpt-bridge non disponibili in questa sessione. Se la porta 4000 e' occupata da un altro processo, chiudilo."
exit 0
