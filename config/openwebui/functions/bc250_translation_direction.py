"""Apply the tested BC-250 Stage-2E direction wrapper to translation roles."""

DE_FR_MODEL = "bc250-office-translation-de-fr"
FR_DE_MODEL = "bc250-office-translation-fr-de"

WRAPPERS = {
    DE_FR_MODEL: (
        "Translate from German to French. Translate every ordinary-language source word "
        "and preserve the document structure. Return only the translation.\n\n"
        "[CURRENT_SOURCE]\n"
    ),
    FR_DE_MODEL: (
        "Translate from French to German. Translate every ordinary-language source word "
        "and preserve the document structure. Return only the translation.\n\n"
        "[CURRENT_SOURCE]\n"
    ),
}


class Filter:
    async def inlet(self, body: dict) -> dict:
        model_id = body.get("model")
        wrapper = WRAPPERS.get(model_id)
        if wrapper is None:
            raise ValueError(
                f"BC-250 translation direction filter attached to unexpected model: {model_id!r}"
            )

        messages = body.get("messages")
        if not isinstance(messages, list):
            raise ValueError("BC-250 translation role requires a messages list")

        for message in reversed(messages):
            if not isinstance(message, dict) or message.get("role") != "user":
                continue
            content = message.get("content")
            if not isinstance(content, str):
                raise ValueError("BC-250 translation role requires a text-only user message")
            if not content.startswith(wrapper):
                message["content"] = wrapper + content
            return body

        raise ValueError("BC-250 translation role requires a user message")
