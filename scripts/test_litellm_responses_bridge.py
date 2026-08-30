#!/usr/bin/env python
"""Self-check delle funzioni pure del ponte WebSearch (/v1/messages).

Nessuna rete: valida solo parsing SSE, costruzione della risposta Anthropic e
serializzazione SSE. Si lancia con il python del venv LiteLLM:

    ~/.local/share/litellm/venvs/*/Scripts/python.exe scripts/test_litellm_responses_bridge.py
"""
import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULO = os.path.join(_HERE, "litellm-responses-bridge.py")
_spec = importlib.util.spec_from_file_location("litellm_responses_bridge", _MODULO)
assert _spec is not None and _spec.loader is not None, "impossibile caricare " + _MODULO
_m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_m)

SSE = """\
data: {"type":"response.created","response":{"model":"gpt-5.6-sol"}}

data: {"type":"response.output_item.done","item":{"type":"web_search_call","id":"ws_1","status":"completed","action":{"type":"search","queries":["meteo Milano oggi"],"query":"meteo Milano oggi"}}}

data: {"type":"response.output_text.delta","item_id":"m1","delta":"Oggi a Milano "}

data: {"type":"response.output_text.delta","item_id":"m1","delta":"cielo sereno."}

data: {"type":"response.output_text.annotation.added","item_id":"m1","annotation":{"type":"url_citation","url":"https://example.com/milano","title":"Meteo Milano","start_index":0,"end_index":10}}

data: {"type":"response.output_text.annotation.added","item_id":"m1","annotation":{"type":"url_citation","url":"https://example.com/milano","title":"Meteo Milano","start_index":0,"end_index":10}}

data: {"type":"response.completed","response":{"status":"completed","usage":{"input_tokens":100,"output_tokens":50}}}
"""


def _testa():
    # 1. rilevamento tool web search
    assert _m._is_web_search_only([{"type": "web_search_20260209", "name": "web_search"}])
    assert _m._is_web_search_only([{"name": "web_search", "type": "web_search"}])
    assert not _m._is_web_search_only([{"type": "function", "name": "x"}])
    assert not _m._is_web_search_only(None)

    # 2. estrazione query dall'ultimo messaggio user
    assert _m._ultimo_testo_utente([{"role": "user", "content": "query"}]) == "query"
    assert _m._ultimo_testo_utente([{"role": "assistant", "content": "no"}]) is None

    # 3. parsing SSE
    query, citazioni, testo = _m._estrai_web_search(SSE)
    assert query == "meteo Milano oggi", query
    assert testo == "Oggi a Milano cielo sereno.", testo
    assert citazioni == [{"url": "https://example.com/milano", "title": "Meteo Milano"}], citazioni

    # 4. risposta Anthropic
    risposta = _m._costruisci_risposta("claude-gpt-5-6-sol-max", query, citazioni, testo)
    tipi = [b["type"] for b in risposta["content"]]
    assert tipi == ["server_tool_use", "web_search_tool_result", "text"], tipi
    assert risposta["usage"]["server_tool_use"]["web_search_requests"] == 1

    # 5. serializzazione SSE
    sse = _m._sse_antropico(risposta).decode("utf-8")
    assert sse.startswith("event: message_start\n")
    assert "event: content_block_start" in sse
    assert "web_search_tool_result" in sse
    assert "event: message_stop" in sse

    # 6. evento per blocco: ogni content_block_start ha un content_block_stop
    assert sse.count("event: content_block_start") == sse.count("event: content_block_stop")

    print("OK: tutte le verifiche passano")


if __name__ == "__main__":
    try:
        _testa()
    except AssertionError as e:
        print("FAIL:", e, file=sys.stderr)
        sys.exit(1)
