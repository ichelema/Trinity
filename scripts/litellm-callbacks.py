from typing import Optional, Union

from litellm.caching.dual_cache import DualCache
from litellm.integrations.custom_logger import CustomLogger
from litellm.proxy._types import UserAPIKeyAuth
from litellm.types.utils import CallTypesLiteral

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

    Da LiteLLM 1.98 i messaggi `role:system` inline restano nella sequenza e il
    bridge Anthropic -> Responses li traduce nel punto corretto. La callback
    gestisce solo le integrazioni TypingMind ancora mancanti nel proxy.

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

    async def async_pre_call_hook(
        self,
        user_api_key_dict: UserAPIKeyAuth,
        cache: DualCache,
        data: dict,
        call_type: CallTypesLiteral,
    ) -> Optional[Union[Exception, str, dict]]:
        if not self._is_chatgpt(data.get("model", "")):
            return data

        # Da LiteLLM 1.98 il system top-level e i system inline restano intatti:
        # il bridge Anthropic -> Responses li traduce nel punto corretto. Non va
        # più fatto il flattening in `instructions`, che perderebbe la posizione
        # dei messaggi mid-turn.

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
