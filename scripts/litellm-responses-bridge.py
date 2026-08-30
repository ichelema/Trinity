"""Ponte /v1/responses per client che non gestiscono SSE (TypingMind).

Due problemi risolti, entrambi a livello di trasporto HTTP — per questo non
possono stare in ``callbacks.py``, che vede solo i dati Python della chiamata:

1. Il backend ChatGPT (Codex OAuth) risponde SEMPRE in ``text/event-stream``,
   anche quando il client ha chiesto una risposta normale: TypingMind fa
   ``JSON.parse`` sul flusso e fallisce con "Unexpected token 'd', data:...".
   Qui il flusso viene aggregato nell'oggetto ``response`` finale.
   NB: l'evento ``response.completed`` arriva con ``output`` VUOTO — i
   contenuti reali stanno negli eventi ``response.output_item.done``.

2. Le immagini arrivano come item ``image_generation_call`` con il PNG in
   base64 nel campo ``result``: TypingMind non sa renderizzarlo. Il PNG viene
   salvato su disco, servito da ``GET /img/<nome>`` e sostituito da un link
   markdown nel testo del messaggio, che invece viene renderizzato.

PERIMETRO — il ponte si attiva SOLO se valgono tutte queste condizioni:
  - metodo POST sul path esatto ``/v1/responses``;
  - il corpo contiene ``litellm_session_id`` fra quelli abilitati
    (default: ``typingmind``, override con RESPONSES_BRIDGE_SESSIONS);
  - la risposta a monte è davvero ``text/event-stream``.
Con due comportamenti a seconda di cosa ha chiesto il client:
  - senza ``stream``: il flusso viene aggregato in un unico JSON (punto 1);
  - con ``stream``: il flusso SSE passa intatto, ma l'evento finale
    ``response.completed`` viene ricompletato con gli item accumulati —
    da build di metà agosto 2026 TypingMind renderizza da quell'evento
    (vuoto per il difetto del punto 1) e mostrava bolle vuote.
Claude Code (``/v1/messages``) e Hindsight (``/v1/chat/completions``) non
passano di qui in nessun caso.
"""
import base64
import hashlib
import json
import os
import time
import uuid

import httpx

_DIR = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(_DIR, "images")
GIORNI_RITENZIONE = int(os.environ.get("RESPONSES_BRIDGE_RETENTION_DAYS", "7"))
SESSIONI = {s.strip() for s in os.environ.get(
    "RESPONSES_BRIDGE_SESSIONS", "typingmind").split(",") if s.strip()}
PATH = "/v1/responses"
MESSAGES_PATH = "/v1/messages"


# --------------------------------------------------------------------------- #
# WebSearch di Claude Code: /v1/messages -> /v1/responses (web_search nativo)
# --------------------------------------------------------------------------- #
# Claude Code invia la ricerca come richiesta autonoma /v1/messages con un
# tool nativo `web_search_20260...`. Il bridge Messages->Responses di LiteLLM
# 1.98 non lo traduce (usa `web_search_preview`, rifiutato dal backend, e non
# converte `web_search_call`/citazioni). Qui si intercetta SOLO quel caso, si
# inoltra a /v1/responses col tool `web_search` (accettato da ChatGPT Codex) e
# si riconverte la risposta nel formato Anthropic atteso da Claude Code.
# --------------------------------------------------------------------------- #


def _is_web_search_only(tools):
    """True se TUTTI i tool sono web_search nativi Anthropic (nessun tool misto)."""
    if not tools:
        return False
    return all(
        isinstance(t, dict)
        and (str(t.get("type", "")).startswith("web_search_") or t.get("name") == "web_search")
        for t in tools
    )


def _ultimo_testo_utente(messages):
    """Testo dell'ultimo messaggio user (query della ricerca)."""
    for m in reversed(messages or []):
        if not isinstance(m, dict) or m.get("role") != "user":
            continue
        c = m.get("content")
        if isinstance(c, str):
            return c
        if isinstance(c, list):
            testi = [b.get("text", "") for b in c
                     if isinstance(b, dict) and b.get("type") == "text"]
            if testi:
                return " ".join(testi)
    return None


def _estrai_web_search(testo_sse):
    """Da un flusso SSE /v1/responses estrae (query, citazioni, testo finale).

    ``query`` dall'azione del primo ``web_search_call``; ``citazioni`` dalle
    annotation ``url_citation`` (deduplicate per URL); ``testo`` accumulando i
    delta ``output_text.delta``.
    """
    query = None
    citazioni = []
    visti = set()
    testo = []
    for riga in testo_sse.splitlines():
        if not riga.startswith("data: "):
            continue
        dato = riga[6:].strip()
        if not dato or dato == "[DONE]":
            continue
        try:
            ev = json.loads(dato)
        except ValueError:
            continue
        tipo = ev.get("type")
        if tipo == "response.output_item.done":
            item = ev.get("item") or {}
            if item.get("type") == "web_search_call":
                azione = item.get("action") or {}
                if query is None:
                    query = azione.get("query") or (azione.get("queries") or [None])[0]
        elif tipo == "response.output_text.delta":
            testo.append(ev.get("delta", ""))
        elif tipo == "response.output_text.annotation.added":
            ann = ev.get("annotation") or {}
            url = ann.get("url")
            if url and url not in visti:
                visti.add(url)
                citazioni.append({"url": url, "title": ann.get("title", "")})
    return query, citazioni, "".join(testo)


def _costruisci_risposta(model, query, citazioni, testo):
    """Risposta Anthropic non-streaming con server_tool_use + risultato + testo."""
    tool_id = "srvtoolu_" + uuid.uuid4().hex[:24]
    content = [
        {"type": "server_tool_use", "id": tool_id, "name": "web_search",
         "input": {"query": query or ""}},
        {"type": "web_search_tool_result", "tool_use_id": tool_id,
         "content": [
             {"type": "web_search_result", "url": c["url"], "title": c["title"],
              "page_age": None, "encrypted_content": "", "snippet": ""}
             for c in citazioni
         ]},
    ]
    if testo:
        content.append({"type": "text", "text": testo})
    return {
        "id": "msg_" + uuid.uuid4().hex,
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "server_tool_use": {
                "web_search_requests": 1 if query else 0,
                "web_fetch_requests": 0,
            },
        },
    }


def _sse_antropico(risposta):
    """Serializza la risposta Anthropic in eventi SSE streaming.

    Formato: message_start -> (content_block_start/delta/stop per blocco) ->
    message_delta -> message_stop. Per ``server_tool_use`` l'input non va nel
    content_block_start ma in un ``input_json_delta`` (stessa regola del client
    Anthropic nativo).
    """
    def evento(tipo, dato):
        return f"event: {tipo}\ndata: {json.dumps(dato)}\n\n".encode("utf-8")

    uso = risposta.get("usage", {}) or {}
    chunks = [evento("message_start", {"type": "message_start", "message": {
        "id": risposta.get("id"), "type": "message", "role": "assistant",
        "model": risposta.get("model"), "content": [], "stop_reason": None,
        "stop_sequence": None,
        "usage": {"input_tokens": uso.get("input_tokens", 0), "output_tokens": 0},
    }})]

    for indice, blocco in enumerate(risposta.get("content", [])):
        tipo = blocco.get("type")
        if tipo == "text":
            chunks.append(evento("content_block_start", {
                "type": "content_block_start", "index": indice,
                "content_block": {"type": "text", "text": ""}}))
            chunks.append(evento("content_block_delta", {
                "type": "content_block_delta", "index": indice,
                "delta": {"type": "text_delta", "text": blocco.get("text", "")}}))
        elif tipo == "server_tool_use":
            chunks.append(evento("content_block_start", {
                "type": "content_block_start", "index": indice,
                "content_block": {"type": "server_tool_use", "id": blocco.get("id"),
                                  "name": blocco.get("name")}}))
            chunks.append(evento("content_block_delta", {
                "type": "content_block_delta", "index": indice,
                "delta": {"type": "input_json_delta",
                          "partial_json": json.dumps(blocco.get("input", {}))}}))
        else:  # web_search_tool_result: blocco completo nello start
            chunks.append(evento("content_block_start", {
                "type": "content_block_start", "index": indice,
                "content_block": blocco}))
        chunks.append(evento("content_block_stop", {
            "type": "content_block_stop", "index": indice}))

    delta_uso = {"output_tokens": uso.get("output_tokens", 0)}
    if uso.get("input_tokens") is not None:
        delta_uso["input_tokens"] = uso["input_tokens"]
    chunks.append(evento("message_delta", {"type": "message_delta",
        "delta": {"stop_reason": risposta.get("stop_reason"),
                  "stop_sequence": risposta.get("stop_sequence")},
        "usage": delta_uso}))
    chunks.append(evento("message_stop", {"type": "message_stop"}))
    return b"".join(chunks)


LOG_FILE = os.path.join(_DIR, "bridge.log")


def _log(msg):
    print(f"[responses-bridge] {msg}", flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except OSError:
        pass


def _pulisci_vecchie():
    """Le immagini pesano ~2,5 MB l'una: senza pulizia la cartella cresce."""
    if not os.path.isdir(IMG_DIR):
        return
    limite = time.time() - GIORNI_RITENZIONE * 86400
    rimosse = 0
    for nome in os.listdir(IMG_DIR):
        percorso = os.path.join(IMG_DIR, nome)
        try:
            if os.path.isfile(percorso) and os.path.getmtime(percorso) < limite:
                os.remove(percorso)
                rimosse += 1
        except OSError:
            pass
    if rimosse:
        _log(f"pulizia: rimosse {rimosse} immagini più vecchie di {GIORNI_RITENZIONE} giorni")


def _aggrega(testo_sse):
    """Da flusso SSE all'oggetto response finale, con l'output ricostruito."""
    finale = None
    items = []
    for riga in testo_sse.splitlines():
        if not riga.startswith("data: "):
            continue
        dato = riga[6:].strip()
        if not dato or dato == "[DONE]":
            continue
        try:
            ev = json.loads(dato)
        except ValueError:
            continue
        tipo = ev.get("type")
        if tipo == "response.completed" and ev.get("response"):
            finale = ev["response"]
        elif tipo == "response.output_item.done" and ev.get("item"):
            items.append(ev["item"])
    if finale is not None and not finale.get("output") and items:
        finale["output"] = items
    return finale


def _estrai_immagini(finale, base_url):
    """Salva i PNG, li sostituisce con link markdown, alleggerisce il JSON."""
    urls = []
    for item in finale.get("output", []):
        if item.get("type") != "image_generation_call" or not item.get("result"):
            continue
        try:
            raw = base64.b64decode(item["result"])
        except Exception:
            continue
        ext = item.get("output_format") or "png"
        nome = f"{hashlib.sha1(raw).hexdigest()[:16]}.{ext}"
        os.makedirs(IMG_DIR, exist_ok=True)
        with open(os.path.join(IMG_DIR, nome), "wb") as f:
            f.write(raw)
        urls.append(f"{base_url}/img/{nome}")
        item["result"] = ""
    if not urls:
        return 0
    md = "\n\n" + "\n".join(f"![immagine generata]({u})" for u in urls)
    messaggi = [i for i in finale.get("output", []) if i.get("type") == "message"]
    if messaggi:
        parti = messaggi[-1].setdefault("content", [])
        testi = [p for p in parti if isinstance(p, dict) and "text" in p]
        if testi:
            testi[-1]["text"] = (testi[-1].get("text") or "") + md
        else:
            parti.append({"type": "output_text", "text": md, "annotations": []})
    else:
        finale.setdefault("output", []).append({
            "type": "message", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": md, "annotations": []}],
        })
    return len(urls)


class _Ponte:
    """Middleware ASGI puro.

    Non si usa BaseHTTPMiddleware perché per decidere se intervenire va letto
    il corpo della richiesta: quello consumerebbe il canale ``receive`` e il
    proxy resterebbe in attesa di un corpo mai riconsegnato. Qui i messaggi
    vengono bufferizzati e riprodotti intatti a valle.
    """

    def __init__(self, app):
        self.app = app

    async def _gestisci_messages(self, scope, receive, send):
        """Intercetta le richieste /v1/messages di sola ricerca web.

        Se non è una ricerca web (o manca la query), riproduce il corpo
        bufferizzato intatto e lascia fare a LiteLLM.
        """
        messaggi = []
        corpo = b""
        while True:
            m = await receive()
            messaggi.append(m)
            corpo += m.get("body", b"") or b""
            if not m.get("more_body"):
                break

        async def receive_replay():
            if messaggi:
                return messaggi.pop(0)
            return await receive()

        try:
            dati = json.loads(corpo)
        except ValueError:
            return await self.app(scope, receive_replay, send)

        tools = dati.get("tools")
        if not _is_web_search_only(tools):
            return await self.app(scope, receive_replay, send)

        modello = dati.get("model")
        query = _ultimo_testo_utente(dati.get("messages"))
        if not modello or not query:
            return await self.app(scope, receive_replay, send)

        auth = self._auth_da_scope(scope)
        try:
            sse = await self._esegui_ricerca(modello, query, auth)
            q, citazioni, testo = _estrai_web_search(sse)
            risposta = _costruisci_risposta(modello, q or query, citazioni, testo)
        except Exception as e:  # noqa: BLE001 - mai rompere /v1/messages
            _log(f"websearch: ricerca fallita ({e}), passo al flusso normale")
            return await self.app(scope, receive_replay, send)

        corpo_out = _sse_antropico(risposta)
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/event-stream"),
                        (b"content-length", str(len(corpo_out)).encode())],
        })
        await send({"type": "http.response.body", "body": corpo_out, "more_body": False})
        _log(f"websearch: ricerca completata ({len(citazioni)} fonte/i)")

    @staticmethod
    def _auth_da_scope(scope):
        """Credenziali del chiamante, riusate per la chiamata interna."""
        intestazioni = {k.lower(): v for k, v in scope.get("headers") or []}
        auth = {}
        for chiave in (b"authorization", b"x-api-key", b"x-litellm-api-key"):
            if chiave in intestazioni:
                auth[chiave.decode("latin-1")] = intestazioni[chiave].decode("latin-1")
        if not auth:
            master = os.environ.get("LITELLM_MASTER_KEY")
            if master:
                auth["Authorization"] = f"Bearer {master}"
        return auth

    @staticmethod
    async def _esegui_ricerca(modello, query, auth):
        """Chiama /v1/responses col tool nativo ``web_search`` e restituisce l'SSE."""
        host = os.environ.get("LITELLM_HOST", "127.0.0.1")
        port = os.environ.get("LITELLM_PORT", "4000")
        url = f"http://{host}:{port}/v1/responses"
        payload = {
            "model": modello,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": query}]}],
            "tools": [{"type": "web_search"}],
        }
        headers = {"content-type": "application/json", **auth}
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}")
        return resp.text

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("method") != "POST":
            return await self.app(scope, receive, send)
        path = scope.get("path")
        if path == MESSAGES_PATH:
            return await self._gestisci_messages(scope, receive, send)
        if path != PATH:
            return await self.app(scope, receive, send)

        messaggi = []
        corpo = b""
        while True:
            m = await receive()
            messaggi.append(m)
            corpo += m.get("body", b"") or b""
            if not m.get("more_body"):
                break
        coda = list(messaggi)

        async def receive_replay():
            # Esaurito il replay si delega al canale vero: restituire qui un
            # http.disconnect farebbe credere a StreamingResponse che il client
            # se ne sia andato, cancellando la risposta a metà.
            if coda:
                return coda.pop(0)
            return await receive()

        try:
            dati = json.loads(corpo)
            sessione = dati.get("litellm_session_id") in SESSIONI
            streaming = dati.get("stream") in (True, "true")
        except ValueError:
            sessione = streaming = False
        if not sessione:
            return await self.app(scope, receive_replay, send)

        host = dict(scope.get("headers") or {}).get(b"host")
        base_url = "http://" + (host.decode() if host else "127.0.0.1:4000")

        if streaming:
            # Passthrough SSE: si riscrive solo l'evento finale, che il
            # backend manda con output vuoto (i contenuti veri stanno negli
            # output_item.done). Da build di metà agosto 2026 TypingMind
            # renderizza dall'evento finale: senza questo, bolle vuote.
            resto = {"pending": b"", "items": [], "sse": False}

            async def send_stream(message):
                tipo = message["type"]
                if tipo == "http.response.start":
                    intestazioni = {k.lower(): v for k, v in message.get("headers", [])}
                    resto["sse"] = b"text/event-stream" in intestazioni.get(b"content-type", b"")
                    return await send(message)
                if tipo != "http.response.body" or not resto["sse"]:
                    return await send(message)
                buf = resto["pending"] + (message.get("body", b"") or b"")
                more = bool(message.get("more_body"))
                righe = buf.split(b"\n")
                if more:
                    resto["pending"] = righe.pop()   # riga incompleta: al giro dopo
                    coda = b""
                else:
                    resto["pending"] = b""
                    coda = righe.pop()               # chiusura: nulla da trattenere
                corpo_out = b"".join(
                    self._patch_riga(r, resto, base_url) + b"\n" for r in righe) + coda
                await send({"type": "http.response.body",
                            "body": corpo_out, "more_body": more})

            return await self.app(scope, receive_replay, send_stream)

        stato = {"start": None, "sse": False, "buffer": bytearray()}

        async def send_filtrato(message):
            tipo = message["type"]
            if tipo == "http.response.start":
                stato["start"] = message
                intestazioni = {k.lower(): v for k, v in message.get("headers", [])}
                stato["sse"] = b"text/event-stream" in intestazioni.get(b"content-type", b"")
                if not stato["sse"]:
                    await send(message)
                return
            if tipo == "http.response.body":
                if not stato["sse"]:
                    return await send(message)
                stato["buffer"] += message.get("body", b"") or b""
                if message.get("more_body"):
                    return
                await self._concludi(stato, base_url, send)
                return
            await send(message)

        await self.app(scope, receive_replay, send_filtrato)

    @staticmethod
    def _patch_riga(riga, resto, base_url):
        """Accumula gli output_item.done e ricompleta il response.completed."""
        if not riga.startswith(b"data: "):
            return riga
        dato = riga[6:].strip()
        if not dato or dato == b"[DONE]":
            return riga
        try:
            ev = json.loads(dato)
        except ValueError:
            return riga
        tipo = ev.get("type")
        if tipo == "response.output_item.done" and ev.get("item"):
            resto["items"].append(ev["item"])
            return riga
        if tipo == "response.completed" and ev.get("response") is not None:
            finale = ev["response"]
            if not finale.get("output") and resto["items"]:
                finale["output"] = resto["items"]
                _estrai_immagini(finale, base_url)
                _log(f"stream: evento finale ricostruito con {len(resto['items'])} item")
                return b"data: " + json.dumps(ev).encode("utf-8")
        return riga

    async def _concludi(self, stato, base_url, send):
        finale = _aggrega(stato["buffer"].decode("utf-8", errors="replace"))
        if finale is None:
            corpo = b'{"error":{"message":"responses-bridge: flusso SSE senza evento finale"}}'
            stato_http = 502
        else:
            n = _estrai_immagini(finale, base_url)
            corpo = json.dumps(finale).encode("utf-8")
            stato_http = stato["start"]["status"]
            if n:
                _log(f"{n} immagine/i salvate e linkate, risposta {len(corpo)} byte")
        # Si conservano gli header originali (CORS in primis: senza
        # access-control-allow-origin il browser scarta la risposta), si
        # sostituiscono solo quelli legati al corpo, che ora è diverso.
        esclusi = {b"content-type", b"content-length", b"transfer-encoding",
                   b"content-encoding"}
        intestazioni = [(k, v) for k, v in (stato["start"] or {}).get("headers", [])
                        if k.lower() not in esclusi]
        intestazioni += [(b"content-type", b"application/json"),
                         (b"content-length", str(len(corpo)).encode())]
        await send({
            "type": "http.response.start",
            "status": stato_http,
            "headers": intestazioni,
        })
        await send({"type": "http.response.body", "body": corpo, "more_body": False})


def install(app):
    """Aggancia middleware e rotta immagini. Non solleva mai: in caso di
    problemi il proxy deve partire comunque, semplicemente senza il ponte."""
    try:
        from fastapi.responses import FileResponse, JSONResponse

        _pulisci_vecchie()

        @app.get("/img/{nome}", include_in_schema=False)
        async def _immagine(nome: str):
            percorso = os.path.join(IMG_DIR, os.path.basename(nome))
            if not os.path.isfile(percorso):
                return JSONResponse({"error": "immagine non trovata"}, status_code=404)
            return FileResponse(percorso, media_type="image/png",
                                headers={"Cache-Control": "public, max-age=86400"})

        app.add_middleware(_Ponte)
        _log(f"attivo su POST {PATH} per sessioni {sorted(SESSIONI)}; "
             f"websearch su POST {MESSAGES_PATH}; immagini in {IMG_DIR}")
    except Exception as e:  # noqa: BLE001
        _log(f"NON attivato ({e}); il proxy parte normalmente")
