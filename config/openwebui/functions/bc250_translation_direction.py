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


def _modal_candidates(clause: str, token_re: re.Pattern[str]) -> list[re.Match[str]]:
    """Return protected modal spans in source order for bounded polarity checks."""
    return list(token_re.finditer(clause))


def _modal_contexts(
    clause: str, candidates: list[re.Match[str]]
) -> list[tuple[re.Match[str], str, str]]:
    """Bound each modal's context by the neighboring protected modal spans."""
    contexts: list[tuple[re.Match[str], str, str]] = []
    for index, match in enumerate(candidates):
        previous_end = candidates[index - 1].end() if index else 0
        next_start = candidates[index + 1].start() if index + 1 < len(candidates) else len(clause)
        contexts.append(
            (
                match,
                clause[previous_end : match.start()],
                clause[match.end() : next_start],
            )
        )
    return contexts


def _near_french_negation(clause: str, start: int, end: int) -> bool:
    before = clause[max(0, start - 32) : start]
    after = clause[end : end + 40]
    has_ne = bool(re.search(r"(?:\bne\b|\bn['’])", before))
    has_negative = bool(re.search(r"\b(?:pas|jamais|plus)\b", after))
    return has_ne and has_negative


def _de_modality_events(clause: str) -> tuple[str, ...]:
    """Return ordered German modality events, preserving polarity within a clause."""
    folded = clause.casefold()
    events: list[tuple[int, str]] = []
    token_re = re.compile(
        r"\b(?:sollte|sollten|solltest|solltet|muss|müssen|musst|müsst|"
        r"darf|dürfen|darfst|dürft|kann|können|kannst|könnt|erlaubt|verboten|verpflichtet)\b"
    )
    candidates = _modal_candidates(folded, token_re)
    for match, before, after in _modal_contexts(folded, candidates):
        token = match.group(0)
        # Finite German modal negation belongs to that modal only when ``nicht``
        # occurs after it and before the next protected modal. A preceding ``nicht``
        # is relevant only to participial constructions such as ``nicht erlaubt``
        # and ``nicht verpflichtet``. This prevents one negation from leaking onto
        # an adjacent finite modal in a multi-modal clause.
        negated_after = bool(re.search(r"\bnicht\b", after))
        negated_before = bool(re.search(r"\bnicht\b", before))
        event: str | None
        if token.startswith("sollt"):
            event = "recommendation-negated" if negated_after else "recommendation"
        elif token in {"muss", "müssen", "musst", "müsst"}:
            event = "no-obligation" if negated_after else "obligation"
        elif token in {"darf", "dürfen", "darfst", "dürft"}:
            event = "prohibition" if negated_after else "permission"
        elif token in {"kann", "können", "kannst", "könnt"}:
            # Negated können often expresses inability rather than normative prohibition.
            # Leave it unclassified so a positive source permission cannot silently match it.
            event = None if negated_after else "permission"
        elif token == "erlaubt":
            event = "prohibition" if negated_before else "permission"
        elif token == "verboten":
            event = "prohibition"
        else:  # verpflichtet
            event = "no-obligation" if negated_before else "obligation"
        if event is not None:
            events.append((match.start(), event))
    events.sort(key=lambda item: item[0])
    return tuple(event for _, event in events)


def _fr_modality_events(clause: str) -> tuple[str, ...]:
    """Return ordered French modality events, preserving polarity within a clause."""
    folded = clause.casefold()
    events: list[tuple[int, str]] = []

    no_obligation_patterns = (
        r"(?:n['’](?:est|êtes|etes)|ne\s+(?:sommes|sont))\s+pas\s+obligé(?:e|es|s)?\b",
        r"(?:n['’](?:est|êtes|etes)|ne\s+(?:sommes|sont))\s+pas\s+tenu(?:e|es|s)?\b",
        r"n['’](?:a|ont)\s+pas\s+à\b",
    )
    no_obligation_spans: list[tuple[int, int]] = []
    for pattern in no_obligation_patterns:
        for match in re.finditer(pattern, folded):
            events.append((match.start(), "no-obligation"))
            no_obligation_spans.append((match.start(), match.end()))

    token_re = re.compile(
        r"\b(?:devrais|devrait|devrions|devriez|devraient|"
        r"dois|doit|devons|devez|doivent|"
        r"peux|peut|pouvons|pouvez|peuvent|"
        r"autorisé|autorisée|autorisés|autorisées|"
        r"interdit|interdite|interdits|interdites|"
        r"obligé|obligée|obligés|obligées|"
        r"tenu|tenue|tenus|tenues)\b"
    )
    for match in token_re.finditer(folded):
        if any(start <= match.start() < end for start, end in no_obligation_spans):
            continue
        token = match.group(0)
        negated = _near_french_negation(folded, match.start(), match.end())
        event: str
        if token in {"devrais", "devrait", "devrions", "devriez", "devraient"}:
            event = "recommendation-negated" if negated else "recommendation"
        elif token in {"dois", "doit", "devons", "devez", "doivent"}:
            event = "prohibition" if negated else "obligation"
        elif token in {"peux", "peut", "pouvons", "pouvez", "peuvent"} or token.startswith("autoris"):
            event = "prohibition" if negated else "permission"
        elif token.startswith("interdit"):
            event = "prohibition"
        else:  # obligé / tenu
            event = "no-obligation" if negated else "obligation"
        events.append((match.start(), event))
    events.sort(key=lambda item: item[0])
    return tuple(event for _, event in events)


def _modality_sequence(text: str, language: str) -> list[tuple[str, ...]]:
    detector = _de_modality_events if language == "de" else _fr_modality_events
    return [events for clause in _split_clauses(text) if (events := detector(clause))]


def _modality_change_reason(
    source_events: tuple[str, ...], target_events: tuple[str, ...], model_id: str
) -> str:
    if len(source_events) == 1 and len(target_events) == 1:
        source_mode, target_mode = source_events[0], target_events[0]
        if source_mode == "recommendation" and target_mode == "obligation":
            return (
                "recommendation strengthened to obligation (sollte -> doit)"
                if model_id == DE_FR_MODEL
                else "recommendation strengthened to obligation (devrait -> muss)"
            )
        if source_mode == "obligation" and target_mode == "recommendation":
            return (
                "obligation weakened to recommendation (muss -> devrait)"
                if model_id == DE_FR_MODEL
                else "obligation weakened to recommendation (doit -> sollte)"
            )
        if source_mode == "permission" and target_mode == "obligation":
            return (
                "permission strengthened to obligation (darf -> doit)"
                if model_id == DE_FR_MODEL
                else "permission strengthened to obligation (peut -> muss)"
            )
        if source_mode == "obligation" and target_mode == "permission":
            return (
                "obligation weakened to permission (muss -> peut)"
                if model_id == DE_FR_MODEL
                else "obligation weakened to permission (doit -> darf)"
            )
        if source_mode == "prohibition" and target_mode != "prohibition":
            return (
                "prohibition/negation may have been lost (darf nicht)"
                if model_id == DE_FR_MODEL
                else "prohibition/negation may have been lost (ne ... pas)"
            )
        if source_mode == "recommendation-negated" and target_mode == "recommendation":
            return "negative recommendation polarity was lost"
        if source_mode == "recommendation" and target_mode == "recommendation-negated":
            return "recommendation polarity changed"
        if source_mode == "no-obligation" and target_mode == "obligation":
            return "no-obligation strengthened to obligation"
        if source_mode == "obligation" and target_mode == "no-obligation":
            return "obligation weakened to no-obligation"
    if "prohibition" in source_events and "prohibition" not in target_events:
        return "prohibition/negation may have been lost"
    if len(source_events) == len(target_events):
        changed = [
            index
            for index, (source_mode, target_mode) in enumerate(
                zip(source_events, target_events, strict=True)
            )
            if source_mode != target_mode
        ]
        if len(changed) == 1:
            index = changed[0]
            return _modality_change_reason(
                (source_events[index],), (target_events[index],), model_id
            )
    if sorted(source_events) == sorted(target_events) and source_events != target_events:
        return (
            "modality order changed within clause "
            f"({','.join(source_events)} -> {','.join(target_events)})"
        )
    return (
        "clause modality/polarity changed "
        f"({','.join(source_events) or 'none'} -> {','.join(target_events) or 'none'})"
    )


def modality_mismatch(source: str, target: str, model_id: str) -> str | None:
    """Return ordered clause-local modality/polarity mismatches; avoid semantic rewriting."""
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
    for index, (source_events, target_events) in enumerate(
        zip(source_sequence, target_sequence, strict=True), start=1
    ):
        if source_events != target_events:
            return f"clause {index}: {_modality_change_reason(source_events, target_events, model_id)}"
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
