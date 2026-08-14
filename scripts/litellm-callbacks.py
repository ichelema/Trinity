from typing import Literal, Optional, Union

from litellm.caching.caching import DualCache
from litellm.integrations.custom_logger import CustomLogger
from litellm.proxy._types import UserAPIKeyAuth

# Sessioni per cui iniettare i tool provider-native (stesso valore usato dal
# ponte responses_bridge; il client lo manda come `litellm_session_id`).
SESSIONI_TYPINGMIND = {"typingmind"}

# Tool provider-native da accodare. `search_context_size: high` amplia il
# contesto raccolto dalla ricerca web rispetto al 'medium' di default.
# Su image_generation NON si imposta `quality`: il backend la normalizza
# sempre a 'auto' (verificato con low/medium/hd, nessun errore e nessun
# effetto), mentre `moderation` viene rispettata.
TOOL_NATIVI = (
    {
        "type": "web_search",
        "search_context_size": "high",
        # I modelli 5.6 dichiarano web_search_tool_type "text_and_image":
        # senza questo campo la ricerca resta solo testuale.
        "search_content_types": ["text", "image"],
    },
    {"type": "image_generation", "moderation": "low"},
)


class SystemToInstructions(CustomLogger):
    """
    Pre-call hook per i modelli ChatGPT (Codex OAuth) sul proxy LiteLLM.

    Tutto il contesto `system` — il campo top-level del formato Anthropic
    Messages PIÙ ogni messaggio `role:system` inline (additionalContext degli
    hook di Claude Code: recall Hindsight, skill-eval, core-behavior) —
    confluisce in `instructions`.

    Perché `instructions` e non un messaggio `developer`/`system`: nella catena
    anthropic_messages -> litellm.acompletion -> responses, i messaggi con role
    diverso da user/assistant vengono droppati (perdono il ruolo) prima di
    raggiungere il modello, mentre `instructions` arriva integro. È anche il
    canale dove Claude Code colloca già MEMORY.md, quindi il recall — stessa
    categoria, memoria persistente — è di casa accanto ad essa. I `messages`
    restano così con soli user/assistant.

    NB: nel pre-call hook il `model` è l'ALIAS del config (es. claude-gpt-5-5),
    non il nome reale (chatgpt/gpt-5.5): il routing avviene dopo. Per questo il
    match copre sia il prefisso alias `claude-gpt-` sia il reale `chatgpt/`.
    """

    def _is_chatgpt(self, model: str) -> bool:
        m = (model or "").lower()
        return m.startswith("chatgpt/") or m.startswith("claude-gpt-")

    def _effort_configurato(self, model) -> Optional[str]:
        """Effort dichiarato nel config per l'alias, o None.

        Nel config convivono due forme: `reasoning_effort: high` e, per max,
        `reasoning_effort: {effort: max}`.
        """
        try:
            from litellm.proxy.proxy_server import llm_router

            if llm_router is None:
                return None
            for deployment in llm_router.get_model_list(model_name=model) or []:
                valore = (deployment.get("litellm_params") or {}).get("reasoning_effort")
                if isinstance(valore, dict):
                    valore = valore.get("effort")
                if valore:
                    return str(valore)
        except Exception:  # noqa: BLE001 - mai far fallire la richiesta per questo
            pass
        return None

    def _to_str(self, content) -> str:
        """Normalizza string o lista di content-block Anthropic a stringa pura."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return " ".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        return str(content)

    async def async_pre_call_hook(
        self,
        user_api_key_dict: UserAPIKeyAuth,
        cache: DualCache,
        data: dict,
        call_type: Literal[
            "completion",
            "text_completion",
            "embeddings",
            "image_generation",
            "moderation",
            "audio_transcription",
            "pass_through_endpoint",
            "rerank",
            "mcp_call",
            "anthropic_messages",
        ],
    ) -> Optional[Union[Exception, str, dict]]:
        if not self._is_chatgpt(data.get("model", "")):
            return data

        instr_parts = []

        # system top-level (formato Anthropic Messages) -> instructions
        system_content = data.pop("system", None)
        if system_content:
            instr_parts.append(self._to_str(system_content))

        # messaggi role:system inline -> instructions; il resto (user/assistant)
        # resta in messages/input.
        for key in ("messages", "input"):
            items = data.get(key)
            if not isinstance(items, list):
                continue
            kept = []
            for msg in items:
                if isinstance(msg, dict) and msg.get("role") == "system":
                    instr_parts.append(self._to_str(msg.get("content", "")))
                else:
                    kept.append(msg)
            data[key] = kept

        if instr_parts:
            data["instructions"] = "\n\n".join(instr_parts)

        # TypingMind non sa inviare i tool provider-native, e aggiungerli come
        # body param sostituisce l'array dei plugin invece di fondersi con esso
        # (i plugin sparirebbero: canvas, filesystem, ...). Qui si accodano ai
        # tool che il client ha già mandato, così convivono.
        if data.get("litellm_session_id") in SESSIONI_TYPINGMIND:
            tools = data.get("tools")
            if not isinstance(tools, list):
                tools = []
            for nativo in TOOL_NATIVI:
                esistente = next(
                    (t for t in tools
                     if isinstance(t, dict) and t.get("type") == nativo["type"]),
                    None,
                )
                if esistente is None:
                    tools.append(dict(nativo))
                else:
                    # TypingMind manda il tool nudo (es. il toggle "Web
                    # Browser" invia {"type": "web_search"}): si completano i
                    # parametri mancanti senza toccare le scelte del client.
                    for chiave, valore in nativo.items():
                        esistente.setdefault(chiave, valore)
            data["tools"] = tools

            # TypingMind manda un blocco `reasoning` senza effort (osservato:
            # `{}` oppure `{"summary": "auto"}`). Quel blocco sostituisce il
            # valore mappato da reasoning_effort, quindi senza questo innesto
            # il modello ricadrebbe sul default del server (medium) invece di
            # usare l'effort dell'alias scelto.
            reasoning = data.get("reasoning")
            if isinstance(reasoning, dict) and not reasoning.get("effort"):
                effort = self._effort_configurato(data.get("model"))
                if effort:
                    reasoning["effort"] = effort

        return data


proxy_handler_instance = SystemToInstructions()
