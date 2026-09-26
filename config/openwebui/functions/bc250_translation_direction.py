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
        "German sollte must stay a recommendation (French devrait), never doit; true muss/doit obligations must remain obligations. "
        "Return only the translation.\n\n"
        "[CURRENT_SOURCE]\n"
    ),
    FR_DE_MODEL: (
        "Translate from French to German. Translate every ordinary-language source word "
        "and preserve the document structure. Preserve legal/contractual modality without "
        "strengthening or weakening obligations, permissions, recommendations or prohibitions. "
        "French devrait must stay a recommendation (German sollte), never muss; true muss/doit obligations must remain obligations. "
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
        target_recommendation = bool(
            re.search(r"\b(?:devrais|devrait|devrions|devriez|devraient)\b", target_folded)
        )
        target_obligation = bool(
            re.search(r"\b(?:dois|doit|devons|devez|doivent)\b", target_folded)
        )
        target_prohibition = bool(
            re.search(
                r"\bne\b[^.!?;]{0,50}\b(?:dois|doit|devons|devez|doivent|peux|peut|pouvons|pouvez|peuvent)\b[^.!?;]{0,30}\bpas\b",
                target_folded,
            )
            or re.search(r"\binterdit(?:e|es|s)?\b", target_folded)
        )
        target_permission = (
            bool(re.search(r"\b(?:peux|peut|pouvons|pouvez|peuvent)\b", target_folded))
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
        source_recommendation = bool(
            re.search(r"\b(?:devrais|devrait|devrions|devriez|devraient)\b", source_folded)
        )
        source_obligation = bool(
            re.search(r"\b(?:dois|doit|devons|devez|doivent)\b", source_folded)
        )
        source_prohibition = bool(
            re.search(
                r"\bne\b[^.!?;]{0,50}\b(?:dois|doit|devons|devez|doivent|peux|peut|pouvons|pouvez|peuvent)\b[^.!?;]{0,30}\bpas\b",
                source_folded,
            )
            or re.search(r"\binterdit(?:e|es|s)?\b", source_folded)
        )
        source_permission = (
            bool(re.search(r"\b(?:peux|peut|pouvons|pouvez|peuvent)\b", source_folded))
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


def decimal_value(raw: str) -> Decimal | None:
    """Normalize one locale-formatted numeric token without collapsing decimals."""
    token = re.sub(r"\s+", "", raw.strip()).replace("'", "").replace("’", "")
    if not token or not re.fullmatch(r"\d[\d.,]*", token):
        return None

    if "." in token and "," in token:
        decimal_sep = "." if token.rfind(".") > token.rfind(",") else ","
        grouping_sep = "," if decimal_sep == "." else "."
        whole_raw, fractional = token.rsplit(decimal_sep, 1)
        whole_groups = whole_raw.split(grouping_sep)
        if (
            not fractional.isdigit()
            or not whole_groups[0].isdigit()
            or any(not part.isdigit() or len(part) != 3 for part in whole_groups[1:])
        ):
            return None
        normalized = "".join(whole_groups) + "." + fractional
    elif "." in token or "," in token:
        separator = "." if "." in token else ","
        parts = token.split(separator)
        if any(not part.isdigit() for part in parts):
            return None
        if len(parts) > 2:
            if all(len(part) == 3 for part in parts[1:]):
                normalized = "".join(parts)
            elif len(parts[-1]) in {1, 2} and all(
                len(part) == 3 for part in parts[1:-1]
            ):
                normalized = "".join(parts[:-1]) + "." + parts[-1]
            else:
                return None
        else:
            whole, fractional = parts
            if whole.lstrip("0") == "" and fractional:
                # Leading-zero forms such as 0.125 and 0,125 are decimals, never 125.
                normalized = whole + "." + fractional
            elif len(fractional) in {1, 2}:
                normalized = whole + "." + fractional
            elif len(fractional) == 3:
                normalized = whole + fractional
            else:
                normalized = whole + "." + fractional
    else:
        normalized = token

    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def numeric_values(text: str) -> set[Decimal]:
    """Return normalized numeric values using the runtime translation contract."""
    values: set[Decimal] = set()
    for match in re.finditer(rf"(?<![\w-])(?P<amount>{_NUMBER_TOKEN})(?![\w-])", text):
        value = decimal_value(match.group("amount"))
        if value is not None:
            values.add(value)
    return values


def _currency_values(text: str) -> set[tuple[str, Decimal]]:
    values: set[tuple[str, Decimal]] = set()
    patterns = (
        rf"\b(?P<code>CHF|EUR|USD)\s*(?P<amount>{_NUMBER_TOKEN})",
        rf"(?P<amount>{_NUMBER_TOKEN})\s*(?P<code>CHF|EUR|USD)\b",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            value = decimal_value(match.group("amount"))
            if value is not None:
                values.add((match.group("code").upper(), value))
    return values


def _percentage_values(text: str) -> set[Decimal]:
    values: set[Decimal] = set()
    for match in re.finditer(rf"(?P<amount>{_NUMBER_TOKEN})\s*%", text):
        value = decimal_value(match.group("amount"))
        if value is not None:
            values.add(value)
    return values


def _integrity_tokens(text: str) -> set[str]:
    """Extract source tokens whose literal preservation is part of the translation contract."""
    # Dates may be rendered in locale-equivalent target-language wording (for
    # example 03.11.2026 -> 3 novembre 2026), so only identifiers whose
    # literal spelling is itself contractual are enforced here.
    patterns = (
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
