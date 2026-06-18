from typing import Literal, Optional, Union

from litellm.caching.caching import DualCache
from litellm.integrations.custom_logger import CustomLogger
from litellm.proxy._types import UserAPIKeyAuth


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

        return data


proxy_handler_instance = SystemToInstructions()
