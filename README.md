# Desert Ant Bench

An independent, reproducible benchmark of seven models exposed by
[`desert-ant-core`](https://github.com/Desert-Ant-Labs/desert-ant-core) 4.1.0 on
Apple silicon.

The repository contains benchmark code, synthetic text controls, machine-readable
results, and a self-contained HTML report. It deliberately excludes model weights,
downloaded datasets, audio recordings, application data, credentials, and private
meeting or call content.

## Video walkthrough

[Watch the 1:45 benchmark and Anna integration demo on YouTube](https://youtu.be/5Ja4aW0w8FE).
The meeting shown in the video is synthetic; the benchmark sections use the public
datasets and authored controls described below.

## What is measured

| Area | Models and checks |
|---|---|
| Speech recognition | Voz vs. whisper.cpp large-v3 on English, Russian, and Spanish FLEURS clips |
| Continuous ASR | Voz vs. Whisper on a 60-second AMI meeting excerpt |
| Speech enhancement | Clear on clean and synthetic-noise controls, including output sample rate |
| Speaker diarization | WHO on two AMI meetings, scored with DER |
| Language identification | Ear on 300 FLEURS clips |
| Text models | Gist, Title, and Toxic on 19 authored synthetic controls |

The current report was produced on a MacBook Air M5. Timing blocks record power,
CPU-idle, and thermal conditions. Results collected on battery or under load are
marked as uncontrolled rather than presented as clean performance measurements.

## Repository layout

| Path | Purpose |
|---|---|
| `native/` | Swift benchmark executable for Voz, WHO, Ear, Clear, and Gist |
| `scripts/prepare.py` | Builds deterministic FLEURS subsets and seeded noisy copies |
| `scripts/run.py` | Runs `asr`, `clear`, `ear`, `who`, `text`, or all stages |
| `scripts/metrics.py` | Computes WER, DER, accuracy, and speed summaries |
| `scripts/continuous.py` | Measures continuous 60-second ASR throughput |
| `scripts/clear_controls.py` | Runs level-normalised Clear controls |
| `scripts/report.py` | Generates the self-contained GitHub Pages report in `docs/index.html` |
| `data/controls.json` | Authored synthetic controls for Gist, Title, and Toxic |
| `results/` | Published machine-readable results used by the report |
| `findings/` | Reproduction notes for three concrete model or SDK findings |

## Data and model prerequisites

Third-party data and model weights are not committed.

- [FLEURS](https://huggingface.co/datasets/google/fleurs), CC BY 4.0. Place the
  `en_us`, `ru_ru`, and `es_419` test TSV and archives under `data/fleurs/` before
  running `scripts/prepare.py`.
- [AMI Meeting Corpus](https://groups.inf.ed.ac.uk/ami/corpus/), CC BY 4.0. Place
  `ES2004a.wav` and `IS1009a.wav` under `data/ami/`; diarization references follow
  `pyannote/AMI-diarization-setup` with the `only_words` scoring region.
- Whisper large-v3 is expected at `models/ggml-whisper-large-v3.bin`, with
  `whisper-cli` available on `PATH`.
- Desert Ant and Hugging Face model downloads are written to the ignored `cache/`
  directory on first use. Review the upstream model licenses before downloading or
  redistributing weights.

The text controls are synthetic. Some are intentionally adversarial and contain
quoted abusive language to test toxicity classification; they are not user data.

## Reproduce

Requirements: macOS 15 or newer, Swift 6.2, Python 3.12 or 3.13, and
[`uv`](https://docs.astral.sh/uv/).

```sh
cd native
swift build -c release
cd ..

uv sync
uv run python scripts/text_models.py --download cache/hf
uv run python scripts/prepare.py
uv run python scripts/run.py all
uv run python scripts/metrics.py
uv run python scripts/clear_controls.py
uv run python scripts/continuous.py
uv run python scripts/report.py
```

Run timing tests while connected to AC power and with an otherwise idle machine.
The generated report is `docs/index.html`; the checked-in copy corresponds to the
published JSON results.

## Interpreting the results

- FLEURS clips are roughly ten seconds long, while Whisper pads inputs to a
  30-second window. Use the continuous-audio section for the fairest speed comparison.
- White noise is a reproducible stress test, not a substitute for real room noise.
- The text set is a targeted behavior probe, not a population-level quality estimate.
- All measurements are from one Apple M5 machine; do not treat them as cross-device SLAs.

## Privacy and publication boundary

This repository contains no recordings, transcripts, or numerical summaries from
private calls or meetings. It also excludes local application workspaces, credentials,
download caches, model weights, raw datasets, video production files, and absolute
paths from the author's machine.

## License

A software license has not yet been selected. Until a license file is added, the code
is available for inspection but no reuse rights are granted. Dataset and model licenses
remain with their respective owners.
