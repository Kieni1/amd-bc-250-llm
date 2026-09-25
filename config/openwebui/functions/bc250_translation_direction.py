"""Apply BC-250 translation direction and bounded legal-modality integrity checks."""

import re
from decimal import Decimal, InvalidOperation

DE_FR_MODEL = "bc250-office-translation-de-fr"
FR_DE_MODEL = "bc250-office-translation-fr-de"

WRAPPERS = {
    DE_FR_MODEL: (
        "Translate from German to French. Translate every ordinary-language source word "
        "and preserve the document structure. Preserve legal/contractual modality without "
        "strengthening or weakening obligations, permissions, recommendations or prohibitions. "
        "Return only the translation.\n\n"
        "[CURRENT_SOURCE]\n"
    ),
    FR_DE_MODEL: (
        "Translate from French to German. Translate every ordinary-language source word "
        "and preserve the document structure. Preserve legal/contractual modality without "
        "strengthening or weakening obligations, permissions, recommendations or prohibitions. "
        "Return only the translation.\n\n"
        "[CURRENT_SOURCE]\n"
    ),
}


def _latest_text(messages: object, role: str) -> str:
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == role and isinstance(message.get("content"), str):
            return message["content"]
    return ""


def _source_text(content: str, wrapper: str) -> str:
    return content.removeprefix(wrapper)


def modality_mismatch(source: str, target: str, model_id: str) -> str | None:
    """Return only high-confidence modality mismatches; avoid semantic rewriting."""
    source_folded = source.casefold()
    target_folded = target.casefold()
    if model_id == DE_FR_MODEL:
        source_recommendation = bool(re.search(r"\bsollt(?:e|en|est|et)\b", source_folded))
        source_obligation = bool(re.search(r"\b(?:muss|müssen|musst|müsst)\b", source_folded))
        source_prohibition = bool(re.search(r"\b(?:darf|dürfen|darfst|dürft)\b[^.!?;]{0,40}\bnicht\b", source_folded))
        source_permission = bool(
            re.search(r"\b(?:darf|dürfen|darfst|dürft)\b", source_folded)
        ) and not source_prohibition
        target_recommendation = bool(re.search(r"\bdevrai(?:t|ent|s|ez)\b", target_folded))
        target_obligation = bool(re.search(r"\b(?:doit|doivent|devez|dois)\b", target_folded))
        target_prohibition = bool(
            re.search(r"\bne\b[^.!?;]{0,50}\b(?:doit|doivent|peut|peuvent)\b[^.!?;]{0,30}\bpas\b", target_folded)
            or re.search(r"\binterdit(?:e|es|s)?\b", target_folded)
        )
        target_permission = (
            bool(re.search(r"\b(?:peut|peuvent|pouvez|peux)\b", target_folded))
            or bool(re.search(r"\bautorisé(?:e|es|s)?\b", target_folded))
        ) and not target_prohibition
        if source_recommendation and not source_obligation and target_obligation and not target_recommendation:
            return "recommendation strengthened to obligation (sollte -> doit)"
        if source_obligation and target_recommendation and not target_obligation:
            return "obligation weakened to recommendation (muss -> devrait)"
        if source_permission and target_obligation and not target_permission:
            return "permission strengthened to obligation (darf -> doit)"
        if source_obligation and target_permission and not target_obligation:
            return "obligation weakened to permission (muss -> peut)"
        if source_prohibition and not target_prohibition:
            return "prohibition/negation may have been lost (darf nicht)"
    elif model_id == FR_DE_MODEL:
        source_recommendation = bool(re.search(r"\bdevrai(?:t|ent|s|ez)\b", source_folded))
        source_obligation = bool(re.search(r"\b(?:doit|doivent|devez|dois)\b", source_folded))
        source_prohibition = bool(
            re.search(r"\bne\b[^.!?;]{0,50}\b(?:doit|doivent|peut|peuvent)\b[^.!?;]{0,30}\bpas\b", source_folded)
            or re.search(r"\binterdit(?:e|es|s)?\b", source_folded)
        )
        source_permission = (
            bool(re.search(r"\b(?:peut|peuvent|pouvez|peux)\b", source_folded))
            or bool(re.search(r"\bautorisé(?:e|es|s)?\b", source_folded))
        ) and not source_prohibition
        target_recommendation = bool(re.search(r"\bsollt(?:e|en|est|et)\b", target_folded))
        target_obligation = bool(re.search(r"\b(?:muss|müssen|musst|müsst)\b", target_folded))
        target_prohibition = bool(
            re.search(r"\b(?:darf|dürfen|darfst|dürft)\b[^.!?;]{0,40}\bnicht\b", target_folded)
            or re.search(r"\bverboten\b", target_folded)
        )
        target_permission = (
            bool(re.search(r"\b(?:darf|dürfen|darfst|dürft)\b", target_folded))
            or bool(re.search(r"\berlaubt\b", target_folded))
        ) and not target_prohibition
        if source_recommendation and not source_obligation and target_obligation and not target_recommendation:
            return "recommendation strengthened to obligation (devrait -> muss)"
        if source_obligation and target_recommendation and not target_obligation:
            return "obligation weakened to recommendation (doit -> sollte)"
        if source_permission and target_obligation and not target_permission:
            return "permission strengthened to obligation (peut -> muss)"
        if source_obligation and target_permission and not target_obligation:
            return "obligation weakened to permission (doit -> darf)"
        if source_prohibition and not target_prohibition:
            return "prohibition/negation may have been lost (ne ... pas)"
    return None


_NUMBER_TOKEN = r"\d(?:[\d\s'’.,]*\d)?"


def _decimal_value(raw: str) -> Decimal | None:
    token = raw.strip().replace(" ", "").replace("'", "").replace("’", "")
    if not token:
        return None
    decimal_pos = max(token.rfind("."), token.rfind(","))
    fractional_digits = len(token) - decimal_pos - 1 if decimal_pos >= 0 else 0
    if decimal_pos >= 0 and fractional_digits in {1, 2}:
        whole = re.sub(r"[.,]", "", token[:decimal_pos]) or "0"
        token = whole + "." + token[decimal_pos + 1 :]
    else:
        token = re.sub(r"[.,]", "", token)
    try:
        return Decimal(token)
    except InvalidOperation:
        return None


def _currency_values(text: str) -> set[tuple[str, Decimal]]:
    values: set[tuple[str, Decimal]] = set()
    patterns = (
        rf"\b(?P<code>CHF|EUR|USD)\s*(?P<amount>{_NUMBER_TOKEN})",
        rf"(?P<amount>{_NUMBER_TOKEN})\s*(?P<code>CHF|EUR|USD)\b",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            value = _decimal_value(match.group("amount"))
            if value is not None:
                values.add((match.group("code").upper(), value))
    return values


def _percentage_values(text: str) -> set[Decimal]:
    values: set[Decimal] = set()
    for match in re.finditer(rf"(?P<amount>{_NUMBER_TOKEN})\s*%", text):
        value = _decimal_value(match.group("amount"))
        if value is not None:
            values.add(value)
    return values


def _integrity_tokens(text: str) -> set[str]:
    """Extract source tokens whose literal preservation is part of the translation contract."""
    patterns = (
        r"\b\d{4}-\d{2}-\d{2}\b",
        r"\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b",
        r"\b[A-Z]{2}\d{2}[A-Z0-9 ]{10,30}\b",
        r"\b(?=[A-Z0-9_-]*[A-Z])(?=[A-Z0-9_-]*\d)[A-Z][A-Z0-9]*(?:[-_][A-Z0-9]+)+\b",
    )
    found: set[str] = set()
    for pattern in patterns:
        found.update(match.group(0).strip() for match in re.finditer(pattern, text, re.IGNORECASE))
    return found


def literal_integrity_mismatch(source: str, target: str) -> str | None:
    target_folded = target.casefold().replace("’", "'")
    for token in sorted(_integrity_tokens(source)):
        normalized = token.casefold().replace("’", "'")
        if normalized not in target_folded:
            return f"source token missing from translation ({token})"
    missing_currency = sorted(_currency_values(source) - _currency_values(target))
    if missing_currency:
        code, amount = missing_currency[0]
        return f"source currency amount missing from translation ({code} {amount})"
    missing_percentages = sorted(_percentage_values(source) - _percentage_values(target))
    if missing_percentages:
        return f"source percentage missing from translation ({missing_percentages[0]}%)"
    return None


def translation_integrity_error(body: dict) -> str | None:
    model_id = body.get("model")
    wrapper = WRAPPERS.get(model_id)
    if wrapper is None:
        return None
    messages = body.get("messages")
    source = _source_text(_latest_text(messages, "user"), wrapper)
    target = _latest_text(messages, "assistant")
    if not source or not target:
        return None
    return modality_mismatch(source, target, model_id) or literal_integrity_mismatch(source, target)


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
            raise TypeError("BC-250 translation role requires a messages list")

        for message in reversed(messages):
            if not isinstance(message, dict) or message.get("role") != "user":
                continue
            content = message.get("content")
            if not isinstance(content, str):
                raise TypeError("BC-250 translation role requires a text-only user message")
            if not content.startswith(wrapper):
                message["content"] = wrapper + content
            return body

        raise ValueError("BC-250 translation role requires a user message")

    async def outlet(self, body: dict) -> dict:
        problem = translation_integrity_error(body)
        if problem is None:
            return body
        messages = body.get("messages")
        if not isinstance(messages, list):
            raise TypeError("BC-250 translation integrity check requires a messages list")
        for message in reversed(messages):
            if isinstance(message, dict) and message.get("role") == "assistant":
                message["content"] = (
                    "Translation withheld: BC-250 detected a possible legal/contractual "
                    f"modality mismatch ({problem}). Please review or retry the translation."
                )
                return body
        raise ValueError("BC-250 translation integrity check could not find assistant output")
