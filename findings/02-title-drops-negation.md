# Title: description drops a negation and reverses the instruction

**Model:** `desert-ant-labs/title` @ `0a7c63976754b2e2af23c9f835218fb88e122dbe` (weights v0.1.0)
**Runtime:** mlx-lm (Python), same prompt string as `Titles.prompt` in `Sources/Title/Title.swift` (SDK 4.1.0), chat template from the repo, temperature 0, max 128 tokens. Apple M5, macOS 26.6.2.

## What happens

Input (en):

> The architecture review has moved from Tuesday to Thursday. Please do not publish the draft before the review. The deployment date has not been agreed.

Output:

> TITLE: Architecture review schedule change
> DESC: The architecture review has shifted from Tuesday to Thursday and **requires the draft to be published before the review date**. …

The source says *do not publish before the review*. The description says the opposite. Deterministic: same output on every run.

A second case, same run (fr):

> La réunion est déplacée de mardi à jeudi. La version actuelle reste un prototype. La date de mise en production n'est pas encore décidée.

> DESC: La réunion est déplacée de mardi à jeudi **et reste un prototype actuel**. …

"Prototype" moved from the product version to the meeting.

## Why it matters

A wrong title is cosmetic. A description that flips a "do not" is a factual error a reader will act on, and in meeting notes or tickets it reads as authoritative. Short negated instructions ("do not merge", "not agreed", "not before review") are common in exactly the transcript clips Title was fine-tuned on.

## Reproduce

```sh
# link to the public bench repo goes here once it is published
uv sync && uv run python scripts/text_models.py --download cache/hf
uv run python scripts/run.py text      # results/text.json, ids en-date and fr-date
```

Inputs are in `data/controls.json` (5 Title controls in en/fr/ru). Other outputs, for context:

- `en-condition` kept both the condition and "not a commitment to deliver on Friday"; the title repeats a phrase ("Data migration data migration process").
- `ru-poc` kept the negations but moved the subject: the speaker's "I am not handing it over" became "checks are not handed over".

## Not checked

- The Swift `Title` API itself (I ran the same weights, template and prompt through mlx-lm; the SDK caps at 96 tokens, I used 128, all outputs are well below either).
- A rate. One of four negation-bearing controls lost its negation; one more swapped an attribute. Five inputs are a probe, not an evaluation.
