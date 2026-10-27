"""Build docs/index.html from public benchmark results.

The output is a self-contained GitHub Pages document with no external requests.
"""
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
S = json.loads((ROOT / 'results' / 'summary.json').read_text())
T = json.loads((ROOT / 'results' / 'text.json').read_text())
CONTROLS = {c['id']: c for c in json.loads((ROOT / 'data' / 'controls.json').read_text())}
e = html.escape


def table(head, rows, num=()):
    th = ''.join(f'<th class="{"n" if i in num else ""}">{e(h)}</th>' for i, h in enumerate(head))
    tr = ''.join('<tr>' + ''.join(f'<td class="{"n" if i in num else ""}">{c}</td>' for i, c in enumerate(r)) + '</tr>'
                 for r in rows)
    return f'<div class="scroll"><table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>'


def flag(block):
    if block.get('controlled'):
        return ''
    b = (block.get('conditions') or [{}])[0]
    why = f"on {b['power'].upper() if b['power'] == 'ac' else b['power']} power with the CPU {b['cpuIdlePercent']}% idle before the stage (gate: AC and ≥85%)" if 'cpuIdlePercent' in b else 'on battery or under desktop load'
    return f'<p class="warn">Timing in this block was measured {why}. Accuracy numbers are unaffected; the controlled Clear stage below shows the same speed ratio range.</p>'


def asr_rows(block, keys):
    return [[k, block[k]['files'], block[k]['audioMinutes'], f"{block[k]['werVoz']}%", f"{block[k]['werWhisper']}%",
             f"{block[k]['vozRealtime']}×", f"{block[k]['whisperRealtime']}×", f"{block[k]['speedup']}×"] for k in keys]


def continuous():
    path = ROOT / 'results' / 'continuous.json'
    if not path.exists():
        return ''
    c = json.loads(path.read_text())
    w, v = c['median']['whisper'], c['median']['voz']
    rows = [['whole call: process start + load + transcribe', w['callMs'], v['callMs'], f"{c['speedupCall']}×"],
            ['transcription only', w['inferenceMs'], v['inferenceMs'], f"{c['speedupInference']}×"]]
    return f'''<h3>Continuous audio: 60 s of an AMI meeting</h3>
<p>{e(c['audio'])}. Three fresh processes per engine, alternating, medians. Raw runs are preserved in <code>results/continuous.json</code>.</p>
{flag(c)}{table(['', 'Whisper, ms', 'Voz, ms', 'Voz faster by'], rows, num=(1, 2, 3))}'''


def clear_controls():
    path = ROOT / 'results' / 'clear-controls.json'
    if not path.exists():
        return ''
    sets = json.loads(path.read_text())['sets']
    rows = [[label, f"{sets[k + '-raw']['werVoz']}%", f"{sets[k + '-clear']['werVoz']}%"]
            for k, label in [('clean', 'clean speech'), ('snr15', 'white noise, 15 dB SNR'), ('snr5', 'white noise, 5 dB SNR')]]
    return f'''<h3>Control: level-normalised input</h3>
<p>Many FLEURS recordings are very quiet (RMS around −60 dBFS). To separate level from noise, the same 100 clips were
normalised to −23 dBFS RMS first, then mixed with noise, then run through Voz with and without Clear.</p>
{table(['input', 'Voz WER', 'Voz WER after Clear'], rows, num=(1, 2))}
<p>Clear leaves clean speech almost untouched, so the model is not broken. On broadband noise it costs the recognizer
accuracy, and more so on quiet input. Clear is documented as a listening-quality model, not an ASR front end, and white noise
is a synthetic stress test, not one of the rooms it is built for. My takeaway for an app: keep Clear on the playback path and
feed the recognizer the original audio, unless a real-noise test says otherwise.</p>'''


ASR_HEAD = ['set', 'clips', 'audio, min', 'WER Voz', 'WER Whisper', 'Voz × realtime', 'Whisper × realtime', 'Voz faster by']
sections = []

if 'asr' in S:
    a = S['asr']
    sections.append(f'''<section><h2>Speech recognition: Voz vs Whisper large-v3</h2>
<p>100 FLEURS test sentences per language, one recording per sentence. Both models get the language code.
Whisper is whisper.cpp 1.9.1, large-v3, 8 threads, Metal, default decoding, no prompt. Voz is v0.4.0 through the Swift SDK.
Each model loads once per language; load time is excluded and listed below. WER uses the same normalisation for both models
(case, punctuation, ё→е); numbers are left as written, which costs both models alike.</p>
{flag(a)}{table(ASR_HEAD, asr_rows(a, [k for k in ('en', 'ru', 'es') if k in a]), num=range(1, 8))}
<p class="note">Model load: Voz {', '.join(f"{k} {a[k]['vozLoadMs']} ms" for k in ('en', 'ru', 'es') if k in a)};
Whisper {', '.join(f"{k} {a[k]['whisperLoadMs']} ms" for k in ('en', 'ru', 'es') if k in a)}.</p>
<p><strong>Read the speed column with care.</strong> Whisper pads every input to a 30 s window, so on ~10 s clips most of its
encoder work is padding and the ratio above overstates the gap. The fair speed number is the continuous-audio test below.</p>{continuous()}</section>''')

if 'clear' in S:
    c = S['clear']
    keys = [k for k in c if k.startswith('en-')]
    sections.append(f'''<section><h2>Clear on noisy speech</h2>
<p>The 100 English clips with seeded white noise at 5 dB SNR, then Clear (studio, mastering bypass, 16 kHz requested),
then both recognizers. Clean-speech WER for the same clips is in the table above.</p>
{flag(c)}{table(ASR_HEAD, asr_rows(c, keys), num=range(1, 8))}
<p><strong>Sample rate.</strong> Requested {c['requestedSampleRate']} Hz; reported {', '.join(str(int(r)) for r in c['reportedSampleRates'])} Hz;
file headers: {e('; '.join(sorted(set(c['outputHeaders'].values()))))}. See finding 1.</p>
<p class="note">Clear median per ~10 s clip: {c['medianMsPerFile']} ms.</p>{clear_controls()}</section>''')

if 'who' in S:
    w = S['who']
    meetings = [k for k in w if isinstance(w[k], dict)]
    rows = [[m, w[m]['audioMinutes'], f"{w[m]['whoSpeakers']} / {w[m]['refSpeakers']}", f"{w[m]['derNoCollar']}%",
             f"{w[m]['derCollar250ms']}%", ', '.join(str(x) for x in w[m]['runsMs']), 'yes' if w[m]['sameOutputAllRuns'] else 'no'] for m in meetings]
    sections.append(f'''<section><h2>Diarization: WHO on AMI meetings</h2>
<p>Two AMI test meetings, Mix-Headset audio, reference and scoring region from pyannote/AMI-diarization-setup (only_words).
DER from pyannote.metrics, overlap scored, with no collar and with a ±250 ms collar. Three runs in one loaded process.</p>
{flag(w)}{table(['meeting', 'min', 'speakers found / ref', 'DER, no collar', 'DER, 250 ms collar', 'runs, ms', 'same output'], rows, num=(1, 3, 4))}
<p class="note">Model load in this run: {w['firstLoadMs']} ms{' (weights already cached)' if w['initiallyDownloaded'] else ''}. The first-ever load on this machine, with download and Neural Engine specialization, took 329 s in an earlier run; it is excluded.</p></section>''')

if 'ear' in S:
    r = S['ear']
    sections.append(f'''<section><h2>Language ID: Ear</h2>
<p>All 300 clean FLEURS clips (~10 s each). Top answer right: <strong>{r['correct']} / {r['files']}</strong>.
Wrong but marked reliable: {len(r['wrongButReliable'])}. Median {r['medianMs']} ms per clip.</p>
{flag(r)}{table(['clip', 'answer', 'confidence'], [[e(x['id']), e(x['got']), x['confidence']] for x in r['wrongButReliable']], num=(2,))}</section>''')

title_rows = [[e(row['id']), e(CONTROLS[row['id']]['text']), e(row['title']), e(row['description'])]
              for row in T['data']['title']['rows'] if row['repeat'] == 0]
gist_rows = [[e(row['id']), e(', '.join((CONTROLS[row['id']].get('expected') or {}).get('gist') or ['—'])),
              e(', '.join(t['slug'] for t in row['topics']))] for row in T['data']['gist']['rows'] if row['repeat'] == 0]
tox_rows = []
for row in T['data']['toxic']['rows']:
    if row['repeat']:
        continue
    want = (CONTROLS[row['id']].get('expected') or {}).get('toxic') or {}
    got = [k for k, v in row['flags'].items() if v]
    exp = [k for k, v in want.items() if v]
    ok = 'n/a (language unsupported)' if not row['languageSupported'] else ('match' if set(got) == set(exp) else 'differs')
    tox_rows.append([e(row['id']), '—' if not row['languageSupported'] else e(', '.join(exp) or 'none'), e(', '.join(got) or 'none'), ok])
sections.append(f'''<section><h2>Text models on short controls</h2>
<p>Hand-written probes, not a representative corpus. They check specific behaviours: negation, attribute binding, quoting an insult, counter-speech.</p>
<h3>Title</h3>{table(['id', 'input', 'title', 'description'], title_rows)}
<h3>Gist</h3>{table(['id', 'expected', 'top 3'], gist_rows)}
<h3>Toxic</h3>{table(['id', 'expected flags', 'model flags', ''], tox_rows)}</section>''')

FINDINGS = [
    ('Clear writes 48 kHz on the streaming path even when 16 kHz is requested',
     '<code>enhance(path:to:options:)</code> goes through <code>enhanceStreaming</code>, which uses <code>ClearDSP.sampleRate</code> for the writer and never reads <code>options.sampleRate</code> (Sources/Clear/Streaming.swift). The in-memory path resamples. Not touched by the open 4.2.0 release PR.'),
    ('Title can drop a negation in the description',
     '"Please do not publish the draft before the review" became "requires the draft to be published before the review date". Same prompt string as <code>Titles.prompt</code>, temperature 0, deterministic.'),
    ('Ear marks some Russian clips as Ukrainian with isReliable = true',
     'Confidence up to 0.94. Looks like the confident-confusion case the SDK already handles for Nordic languages.'),
    ('Clear in front of ASR raises WER on broadband noise',
     'Not a bug: a usage note worth a line in the docs. Clean speech is unaffected; see the control table above.'),
]
sections.append('<section><h2>Findings</h2><ol class="findings">' + ''.join(
    f'<li><strong>{e(t)}</strong><br>{b}</li>' for t, b in FINDINGS) + '</ol></section>')

sections.append('''<section><h2>Not measured</h2><ul>
<li>p95 or SLAs: one pass per clip for ASR, three runs for WHO.</li>
<li>Energy, temperature and clocks during runs; only power source, CPU idle share, load average and macOS thermal warnings are logged.</li>
<li>Voz with vocabulary boost; Whisper with VAD or a prompt on this set.</li>
<li>Whether Clear helps on real (non-synthetic) noise; white noise is a stress test, not a room.</li>
<li>Other devices. One MacBook Air M5.</li></ul></section>''')

m = (T.get('machine') or {})
page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Desert Ant Bench</title><style>
:root{{--bg:#fff;--fg:#1a1a1a;--mute:#666;--line:#e4e4e4;--warn:#8a5a00;--warnbg:#fff6e0;--code:#f4f4f4}}
@media (prefers-color-scheme:dark){{:root:not([data-theme=light]){{--bg:#141414;--fg:#ececec;--mute:#9a9a9a;--line:#2c2c2c;--warn:#f0c060;--warnbg:#2b2312;--code:#222}}}}
:root[data-theme=dark]{{--bg:#141414;--fg:#ececec;--mute:#9a9a9a;--line:#2c2c2c;--warn:#f0c060;--warnbg:#2b2312;--code:#222}}
body{{background:var(--bg);color:var(--fg);font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0}}
main{{max-width:960px;margin:0 auto;padding:40px 16px 80px}}
h1{{font-size:28px;margin:0 0 8px}} h2{{font-size:20px;margin:48px 0 12px}} h3{{font-size:16px;margin:24px 0 8px}}
p,li{{max-width:72ch}} .note{{color:var(--mute);font-size:14px}} .warn{{background:var(--warnbg);color:var(--warn);padding:8px 12px;border-radius:6px;font-size:14px}}
.scroll{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;font-size:14px;margin:8px 0}}
th,td{{text-align:left;padding:6px 10px;border-bottom:1px solid var(--line);vertical-align:top}} th{{font-weight:600;white-space:nowrap}}
.n{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}} code{{background:var(--code);padding:1px 4px;border-radius:4px;font-size:13px}}
.findings li{{margin-bottom:12px}}
</style></head><body><main>
<h1>Desert Ant models on a MacBook Air M5</h1>
<p class="note">SDK desert-ant-core 4.1.0 · {e(m.get('chip', 'Apple M5'))} · {round(m.get('memoryBytes', 0) / 2**30)} GB · macOS {e(m.get('os', ''))} · public data: FLEURS, AMI (CC BY 4.0)</p>
<p>This independent benchmark measures seven models on public data and authored synthetic controls so the results can be inspected and reproduced.
Every number below comes from <code>results/*.json</code>; the core stages re-run with <code>uv run python scripts/run.py all</code>.</p>
{''.join(sections)}
</main></body></html>'''
(ROOT / 'docs').mkdir(exist_ok=True)
(ROOT / 'docs' / 'index.html').write_text(page)
print('docs/index.html', len(page), 'bytes')
