"""Apply BC-250 translation direction and bounded translation integrity checks."""

import re
import unicodedata
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


def _split_clauses(text: str) -> list[str]:
    """Split text into bounded sentence/clause units for local modality checks."""
    return [part.strip() for part in re.split(r"(?:[.!?;]+|\n+)", text) if part.strip()]


def _modal_candidates(
    text: str, patterns: tuple[tuple[str, str], ...]
) -> list[tuple[int, int, str]]:
    candidates = [
        (match.start(), match.end(), mode)
        for pattern, mode in patterns
        for match in re.finditer(pattern, text)
    ]
    return sorted(candidates, key=lambda item: (item[0], item[1]))


def _modal_contexts(
    text: str, candidates: list[tuple[int, int, str]]
) -> list[tuple[int, int, str, str, str]]:
    contexts: list[tuple[int, int, str, str, str]] = []
    for index, (start, end, mode) in enumerate(candidates):
        previous_end = candidates[index - 1][1] if index else 0
        next_start = (
            candidates[index + 1][0]
            if index + 1 < len(candidates)
            else len(text)
        )
        contexts.append(
            (start, end, mode, text[previous_end:start], text[end:next_start])
        )
    return contexts


def _de_modality_events(clause: str) -> tuple[str, ...]:
    """Return protected German modality events in source order."""
    folded = clause.casefold()
    candidates = _modal_candidates(
        folded,
        (
            (r"\bsollt(?:e|en|est|et)\b", "recommendation"),
            (r"\b(?:muss|müssen|musst|müsst)\b", "obligation"),
            (r"\b(?:darf|dürfen|darfst|dürft)\b", "permission"),
            (r"\berlaubt\b", "permission"),
            (r"\bverpflichtet\b", "obligation"),
            (r"\bverboten\b", "prohibition"),
        ),
    )

    events: list[str] = []
    for start, end, mode, before, after in _modal_contexts(folded, candidates):
        token = folded[start:end]
        negated_after = bool(re.search(r"\bnicht\b", after))
        negated_before = bool(re.search(r"\bnicht\b", before))
        negated = negated_after or (
            token in {"erlaubt", "verpflichtet"} and negated_before
        )
        if mode == "recommendation":
            events.append("recommendation-negative" if negated else "recommendation")
        elif mode == "obligation":
            events.append("no-obligation" if negated else "obligation")
        elif mode == "permission":
            events.append("prohibition" if negated else "permission")
        else:
            events.append(mode)
    return tuple(events)


def _fr_modality_events(clause: str) -> tuple[str, ...]:
    """Return protected French modality events in source order."""
    folded = clause.casefold()
    candidates = _modal_candidates(
        folded,
        (
            (r"\b(?:devrais|devrait|devrions|devriez|devraient)\b", "recommendation"),
            (r"\b(?:dois|doit|devons|devez|doivent)\b", "obligation"),
            (r"\b(?:peux|peut|pouvons|pouvez|peuvent)\b", "permission"),
            (r"\bautorisé(?:e|es|s)?\b", "permission"),
            (r"\bobligé(?:e|es|s)?\b", "obligation"),
            (r"\binterdit(?:e|es|s)?\b", "prohibition"),
        ),
    )

    events: list[str] = []
    for start, end, mode, before, after in _modal_contexts(folded, candidates):
        has_ne = bool(re.search(r"(?:\bne\b|\bn['’])", before))
        has_negative_particle = bool(
            re.search(r"\b(?:pas|jamais|plus)\b", before)
            or re.search(r"\b(?:pas|jamais|plus)\b", after)
        )
        negated = has_ne and has_negative_particle

        if mode == "recommendation":
            events.append("recommendation-negative" if negated else "recommendation")
        elif mode == "obligation":
            no_obligation = negated and (
                "nécessairement" in after or folded[start:end].startswith("oblig")
            )
            if no_obligation:
                events.append("no-obligation")
            elif negated:
                events.append("prohibition")
            else:
                events.append("obligation")
        elif mode == "permission":
            events.append("prohibition" if negated else "permission")
        else:
            events.append(mode)
    return tuple(events)


def _modality_sequence(text: str, language: str) -> list[tuple[str, ...]]:
    detector = _de_modality_events if language == "de" else _fr_modality_events
    return [events for clause in _split_clauses(text) if (events := detector(clause))]


def _modality_change_reason(
    source_modes: tuple[str, ...], target_modes: tuple[str, ...], model_id: str
) -> str:
    if source_modes == ("recommendation",) and target_modes == ("obligation",):
        return (
            "recommendation strengthened to obligation (sollte -> doit)"
            if model_id == DE_FR_MODEL
            else "recommendation strengthened to obligation (devrait -> muss)"
        )
    if source_modes == ("obligation",) and target_modes == ("recommendation",):
        return (
            "obligation weakened to recommendation (muss -> devrait)"
            if model_id == DE_FR_MODEL
            else "obligation weakened to recommendation (doit -> sollte)"
        )
    if source_modes == ("permission",) and target_modes == ("obligation",):
        return (
            "permission strengthened to obligation (darf -> doit)"
            if model_id == DE_FR_MODEL
            else "permission strengthened to obligation (peut -> muss)"
        )
    if source_modes == ("obligation",) and target_modes == ("permission",):
        return (
            "obligation weakened to permission (muss -> peut)"
            if model_id == DE_FR_MODEL
            else "obligation weakened to permission (doit -> darf)"
        )
    if (
        source_modes == ("recommendation-negative",)
        and target_modes == ("recommendation",)
    ):
        return "recommendation negation/polarity was lost"
    if source_modes == ("no-obligation",) and target_modes == ("obligation",):
        return "absence of obligation was strengthened to obligation"
    if "prohibition" in source_modes and "prohibition" not in target_modes:
        return "prohibition/negation may have been lost"
    source_label = ",".join(source_modes) or "none"
    target_label = ",".join(target_modes) or "none"
    return f"clause modality sequence changed ({source_label} -> {target_label})"


def modality_mismatch(source: str, target: str, model_id: str) -> str | None:
    """Return bounded clause-local modality mismatches; avoid semantic rewriting."""
    if model_id == DE_FR_MODEL:
        source_language, target_language = "de", "fr"
    elif model_id == FR_DE_MODEL:
        source_language, target_language = "fr", "de"
    else:
        return None

    source_sequence = _modality_sequence(source, source_language)
    if not source_sequence:
        return None
    target_sequence = _modality_sequence(target, target_language)
    if len(source_sequence) != len(target_sequence):
        return (
            "modality-bearing clause count changed "
            f"({len(source_sequence)} -> {len(target_sequence)})"
        )
    for index, (source_modes, target_modes) in enumerate(
        zip(source_sequence, target_sequence, strict=True), start=1
    ):
        if source_modes != target_modes:
            reason = _modality_change_reason(source_modes, target_modes, model_id)
            return f"clause {index}: {reason}"
    return None


_NUMBER_TOKEN = r"\d(?:[\d\s'’.,]*\d)?"


def decimal_interpretations(raw: str) -> frozenset[Decimal]:
    """Return every plausible value for one locale-formatted numeric token.

    Single-separator forms with exactly three trailing digits are intentionally
    ambiguous (for example ``1,234`` may mean 1.234 or 1234).  Integrity checks
    compare the complete interpretation set, so translating an ambiguous source
    token to only one of those values fails closed instead of silently accepting
    a possible 1000x change.
    """
    token = re.sub(r"\s+", "", raw.strip()).replace("'", "").replace("’", "")
    if not token or not re.fullmatch(r"\d[\d.,]*", token):
        return frozenset()

    normalized_values: set[str] = set()
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
            return frozenset()
        normalized_values.add("".join(whole_groups) + "." + fractional)
    elif "." in token or "," in token:
        separator = "." if "." in token else ","
        parts = token.split(separator)
        if any(not part.isdigit() for part in parts):
            return frozenset()
        if len(parts) > 2:
            if all(len(part) == 3 for part in parts[1:]):
                normalized_values.add("".join(parts))
            elif len(parts[-1]) in {1, 2} and all(
                len(part) == 3 for part in parts[1:-1]
            ):
                normalized_values.add("".join(parts[:-1]) + "." + parts[-1])
            else:
                return frozenset()
        else:
            whole, fractional = parts
            if (whole.lstrip("0") == "" and fractional) or len(fractional) in {1, 2}:
                normalized_values.add(whole + "." + fractional)
            elif len(fractional) == 3:
                # Preserve both plausible meanings; callers must prove a safe match.
                normalized_values.add(whole + "." + fractional)
                normalized_values.add(whole + fractional)
            else:
                normalized_values.add(whole + "." + fractional)
    else:
        normalized_values.add(token)

    values: set[Decimal] = set()
    for normalized in normalized_values:
        try:
            values.add(Decimal(normalized))
        except InvalidOperation:
            return frozenset()
    return frozenset(values)


def decimal_value(raw: str) -> Decimal | None:
    """Return an unambiguous value, or ``None`` when the token is ambiguous."""
    values = decimal_interpretations(raw)
    if len(values) != 1:
        return None
    return next(iter(values))


def numeric_values(text: str) -> set[Decimal]:
    """Return every plausible value using the runtime translation numeric authority."""
    values: set[Decimal] = set()
    for match in re.finditer(rf"(?<![\w-])(?P<amount>{_NUMBER_TOKEN})(?![\w-])", text):
        values.update(decimal_interpretations(match.group("amount")))
    return values


def _currency_signatures(text: str) -> set[tuple[str, frozenset[Decimal]]]:
    values: set[tuple[str, frozenset[Decimal]]] = set()
    patterns = (
        rf"\b(?P<code>CHF|EUR|USD)\s*(?P<amount>{_NUMBER_TOKEN})",
        rf"(?P<amount>{_NUMBER_TOKEN})\s*(?P<code>CHF|EUR|USD)\b",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            interpretations = decimal_interpretations(match.group("amount"))
            if interpretations:
                values.add((match.group("code").upper(), interpretations))
    return values


def _percentage_signatures(text: str) -> set[frozenset[Decimal]]:
    values: set[frozenset[Decimal]] = set()
    for match in re.finditer(rf"(?P<amount>{_NUMBER_TOKEN})\s*%", text):
        interpretations = decimal_interpretations(match.group("amount"))
        if interpretations:
            values.add(interpretations)
    return values


def _format_interpretations(values: frozenset[Decimal]) -> str:
    return " / ".join(str(value) for value in sorted(values))


_PRESENTATION_HYPHENS = str.maketrans(
    {"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-"}
)


def _literal_match_text(text: str) -> str:
    """Normalize presentation-only Unicode differences for contractual literals."""
    normalized = unicodedata.normalize("NFKC", text).translate(_PRESENTATION_HYPHENS)
    normalized = normalized.replace("’", "'").casefold()
    return " ".join(normalized.split())


def _integrity_tokens(text: str) -> set[str]:
    """Extract source tokens whose literal preservation is part of the translation contract."""
    # Dates may be rendered in locale-equivalent target-language wording (for
    # example 03.11.2026 -> 3 novembre 2026), so only identifiers whose
    # literal spelling is itself contractual are enforced here. Normalize
    # presentation-only Unicode hyphen/space variants before extraction so the
    # source and translated identifier contract uses the same canonical form.
    normalized_text = _literal_match_text(text).upper()
    patterns = (
        r"\b[A-Z]{2}\d{2}[A-Z0-9 ]{10,30}\b",
        r"\b(?=[A-Z0-9_-]*[A-Z])(?=[A-Z0-9_-]*\d)[A-Z][A-Z0-9]*(?:[-_][A-Z0-9]+)+\b",
    )
    found: set[str] = set()
    for pattern in patterns:
        found.update(
            match.group(0).strip()
            for match in re.finditer(pattern, normalized_text, re.IGNORECASE)
        )
    return found


def literal_integrity_mismatch(source: str, target: str) -> str | None:
    target_folded = _literal_match_text(target)
    for token in sorted(_integrity_tokens(source)):
        normalized = _literal_match_text(token)
        if normalized not in target_folded:
            return f"source token missing from translation ({token})"
    missing_currency = _currency_signatures(source) - _currency_signatures(target)
    if missing_currency:
        code, interpretations = min(
            missing_currency, key=lambda item: (item[0], tuple(sorted(item[1])))
        )
        return (
            "source currency amount missing from translation "
            f"({code} {_format_interpretations(interpretations)})"
        )
    missing_percentages = _percentage_signatures(source) - _percentage_signatures(target)
    if missing_percentages:
        interpretations = min(
            missing_percentages, key=lambda item: tuple(sorted(item))
        )
        return (
            "source percentage missing from translation "
            f"({_format_interpretations(interpretations)}%)"
        )
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
                    "Translation withheld: BC-250 detected a possible translation "
                    f"integrity mismatch ({problem}). Please review or retry the translation."
                )
                return body
        raise ValueError("BC-250 translation integrity check could not find assistant output")
