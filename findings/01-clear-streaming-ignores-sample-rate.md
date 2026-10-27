# Clear: `enhance(path:to:options:)` ignores `Options.sampleRate` and always writes 48 kHz

**SDK:** `desert-ant-core` 4.1.0 (Swift, macOS 26.6.2, Apple M5). Also present on `main` in the open 4.2.0 release PR, which doesn't touch `Sources/Clear/Streaming.swift`.

## What happens

```swift
let clear = Clear()
let options = Clear.Options(mastering: .bypass, sampleRate: 16_000)
let result = try await clear.enhance(path: input, to: output, options: options)
// result.sampleRate == 48000, and the file header says 48000 Hz
```

100 of 100 files: requested 16000, `Result.sampleRate` 48000, `afinfo` reports `1 ch, 48000 Hz, Int16`.

## Why

When an output path is given, `enhance(path:to:options:progress:)` takes the bounded-memory branch and calls `enhanceStreaming`. That function sets

```swift
let sampleRate = ClearDSP.sampleRate
```

and uses it for the reader, the loudness meter and `AudioIO.StreamingWriter(to:sampleRate:…)`. `options.sampleRate` is never read on that path. The in-memory path (`enhance(channels:sampleRate:options:)`, used by `enhance(bytes:)` and by `enhance(path:)` without an output) resamples to `options.sampleRate` at the end, so the two entry points disagree.

## Expected

Either resample to `options.sampleRate` before writing in `enhanceStreaming`, or document that file output is always 48 kHz and drop the option on that path. A caller who asks for 16 kHz to feed a recognizer currently gets 3× the samples and a header they did not ask for, with no error.

## Reproduce

```sh
cd native && swift build -c release && cd ..
uv run python scripts/run.py clear
jq '.data.clear.rows[0] | {requestedSampleRate, reportedSampleRate}' results/clear.json
```

## Not checked

- Android / web / Linux bindings.
- Whether `clear-natural` behaves the same (only `clear-studio`, the default, was run).
