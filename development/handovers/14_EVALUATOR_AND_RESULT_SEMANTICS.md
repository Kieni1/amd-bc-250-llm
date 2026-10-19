# Evaluator and result semantics

This file preserves evaluator lessons that prevent false PASS/FAIL results. Keep it even as benchmark implementation is simplified.

## Visible response vs hidden thinking

A thinking-capable model can consume output budget in hidden reasoning and produce an empty visible response.

Therefore:

```text
visible answer present      -> eligible for visible-response identity/evaluation
thinking only               -> not visible-response determinism evidence
empty visible answer        -> do not hash empty string as successful answer identity
```

Hidden thinking must never be substituted for the user-visible answer.

## Result classes

Do not collapse all non-PASS outcomes into one failure.

Useful semantic states:

```text
PASS
QUALITY_FAIL
INCOMPLETE
RUNTIME_FAIL
HARNESS_ERROR
SKIPPED
REVIEW
```

Examples:

- clean reasoning-budget exhaustion with no visible answer may be `INCOMPLETE`;
- repeated/degenerate output remains a quality signal;
- transport/runtime failure is not a quality verdict;
- parser crash is a harness error until raw evidence proves otherwise.

## Preserve raw output

Store the raw model/API response needed to recompute verdicts later. Evaluator fixes should not require rerunning expensive model work when the original evidence is adequate.

## Metamorphic testing principle

For semantic normalizers/evaluators, pair:

```text
positive variants — same meaning, different surface form
negative variants — materially changed meaning
```

A normalization is acceptable only if it preserves intended positives **and** keeps nearby negatives rejected.

Useful positive/negative families include:

- dates with unambiguous equivalent formatting vs changed date;
- `10 AM` / `10:00` where contract allows vs `11 AM`;
- equivalent invoice identifier rendering vs a different identifier;
- grouped citation membership vs a neighboring/incorrect citation;
- correct number appearing before/after explanation vs a different final answer;
- punctuation/case/formatting changes vs polarity/negation/modality changes.

## Do not broaden fuzzy matching casually

Every new normalizer should have negative controls. If making a positive variant pass also makes a nearby wrong answer pass, the normalizer is a defect.

Clause-local meaning matters. Global keyword/set checks can miss polarity or recommendation/obligation changes.

## One semantic authority

Where multiple paths evaluate the same concept (benchmark, revalidation, package smoke), prefer one shared semantic helper rather than copy/pasted parsers that drift.

But do not create a large evaluator framework for only one or two simple rules. Shared authority should reduce code, not expand it.

## Benchmark scope during simplification

The current source test suite intentionally keeps only a small benchmark semantic contract. Do not rebuild the old benchmark qualification suite unless a product decision genuinely depends on it.
