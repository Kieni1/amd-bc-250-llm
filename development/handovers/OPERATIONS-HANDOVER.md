# Operations boundary handover — clean core

## 1. Operator mental model

The normal user should see an appliance, not an engineering console.

The core should boot stock, expose the web interface, run the AI runtime, manage models/documents and clearly report problems/actions.

## 2. GFX removal from operator surface

After clean-core reconstruction there should be no current operator instructions for:

- `bc250 gfx1013 ...`;
- patched boot staging;
- private RADV;
- GFX stock rollback;
- GFX benchmark A1/B/A2.

Historical docs may retain them only in clearly archived material.

## 3. Installer completion

Preserve the useful one-next-action hierarchy from later work where applicable.

Do not add optional experimental guidance that competes with required core actions.

## 4. Status / doctor-or-health / verify

During reconstruction preserve the existing 1.9 contract first. Later generic 2.2 monitoring improvements may be selectively reimplemented.

Do not import GFX state abstractions.

General intent:

- `status`: current informational state;
- health/doctor: operator-facing health/action gate according to the chosen public command contract;
- `verify`: deeper systematic package/config/runtime validation.

## 5. Human wording

Accepted generic UX direction:

- `Web interface` rather than `front door`;
- concise user-visible cause before implementation detail;
- one required next action;
- exact internals remain available in diagnostic/machine output.

## 6. Color

TTY-only, `NO_COLOR` aware, text-complete without color.

Use consistent semantic colors as documented in the main working rules.

## 7. Model UX

Forward-port safe cancel/no-mutation wording and clearer selection prompts.

Do not rename product categories automatically.

## 8. Documentation entry points

Keep README/TLDR focused on normal core operation. Topic docs hold deeper maintenance/rationale.

Do not make users read archived GFX documentation to understand the normal appliance.
