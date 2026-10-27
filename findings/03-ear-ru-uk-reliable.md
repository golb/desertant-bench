# Ear: Russian labelled as Ukrainian with `isReliable == true`

**Model:** Ear, SDK `desert-ant-core` 4.1.0, revision `v0.2.0`. Apple M5, macOS 26.6.2.

## What happens

On 300 FLEURS test clips (100 each en / ru / es, one recording per sentence, ~10 s each), Ear's top answer was right 294 times (98.0%, in line with the 98.0–99.6% at 10 s in `docs/models/ear.md`).

Of the 6 misses, 3 came back with `isReliable == true`, all on Russian:

| clip | expected | got | confidence | reliable |
|---|---|---|---:|---|
| ru-1737 | ru | uk | 0.941 | true |
| ru-1689 | ru | uk | 0.860 | true |
| ru-1724 | ru | hr | 0.585 | true |

(Full rows in `results/summary.json` → `ear.wrongButReliable`.) The other three misses (two en, one ru→uk) were correctly flagged unreliable.

## Why it matters

The docs say to branch on `isReliable`, and the Nordic languages are already forced unreliable because the detector "confuses them with each other confidently rather than uncertainly, so a margin test cannot catch it". Russian→Ukrainian at 0.94 looks like the same failure mode. Routing Russian speech to a Ukrainian recognizer (or the reverse) on a "reliable" answer gives fluent wrong text, which is worse than asking the user.

## Question

Is ru/uk (and maybe other close Slavic pairs) a candidate for `confusableLanguages`, or is this expected at 10 s and fixed by passing the full 30 s? The docs recommend 30 s for room recordings; FLEURS is close-mic read speech, so I did not expect short clips to be the issue.

## Reproduce

```sh
uv run python scripts/prepare.py        # FLEURS subset, data/manifest.json
uv run python scripts/run.py ear && uv run python scripts/metrics.py
```

## Not checked

- 30 s inputs (concatenated clips) for the same speakers.
- Whether the 3 clips share a speaker. 100 Russian clips is too few for a rate.
