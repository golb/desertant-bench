"""Score results/*.json into results/summary.json (WER, DER, accuracy, speed)."""
import json
import re
import statistics
import unicodedata
from pathlib import Path

import jiwer
from pyannote.core import Annotation, Segment, Timeline
from pyannote.metrics.diarization import DiarizationErrorRate

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / 'results'
MANIFEST = {m['id']: m for m in json.loads((ROOT / 'data' / 'manifest.json').read_text())}


def norm(text):
    # Same normalisation for both models: case, punctuation, ё, whitespace.
    # Numbers are left as written, which costs both models alike.
    text = unicodedata.normalize('NFKC', text).lower().replace('ё', 'е')
    text = ''.join(' ' if unicodedata.category(c)[0] in 'PS' else c for c in text)
    return re.sub(r'\s+', ' ', text).strip()


def wer(pairs):
    refs, hyps = zip(*[(norm(r), norm(h)) for r, h in pairs])
    return round(100 * jiwer.wer(list(refs), list(hyps)), 2)


def asr_block(langs, suffix=''):
    out = {}
    for lang, d in langs.items():
        voz = {r['id']: r for r in d['voz']['rows'] if r['repeat'] == 0}
        ids = list(voz)
        ref = lambda i: MANIFEST[i.removesuffix('-clear')]['reference']
        audio = d['audioSeconds']
        voz_ms = sum(voz[i]['callMs'] for i in ids)
        whisper_ms = d['whisper']['wallMs'] - d['whisper']['loadMs']
        out[lang + suffix] = {
            'files': len(ids), 'audioMinutes': round(audio / 60, 1),
            'werVoz': wer([(ref(i), voz[i]['text']) for i in ids]),
            'werWhisper': wer([(ref(i), d['whisper']['texts'][i]) for i in ids]),
            'vozLoadMs': round(d['voz']['loadMs']), 'whisperLoadMs': round(d['whisper']['loadMs']),
            'vozMs': round(voz_ms), 'whisperMs': round(whisper_ms),
            'vozRealtime': round(audio * 1000 / voz_ms, 1), 'whisperRealtime': round(audio * 1000 / whisper_ms, 1),
            'speedup': round(whisper_ms / voz_ms, 1),
        }
    return out


def der(who):
    metric0, metric25 = DiarizationErrorRate(), DiarizationErrorRate(collar=0.5)  # pyannote collar is total width
    out = {}
    for meeting in sorted({r['id'] for r in who['rows']}):
        rows = [r for r in who['rows'] if r['id'] == meeting]
        ref = Annotation()
        for line in (ROOT / 'data' / 'ami' / f'{meeting}.rttm').read_text().splitlines():
            p = line.split()
            ref[Segment(float(p[3]), float(p[3]) + float(p[4]))] = p[7]
        _, _, start, end = (ROOT / 'data' / 'ami' / f'{meeting}.uem').read_text().split()
        uem = Timeline([Segment(float(start), float(end))])
        hyp = Annotation()
        for t in rows[0]['turns']:
            hyp[Segment(t['start'], t['end'])] = f"S{t['speaker']}"
        out[meeting] = {'audioMinutes': round(float(end) / 60, 1),
                        'refSpeakers': len(ref.labels()), 'whoSpeakers': rows[0]['speakerCount'],
                        'derNoCollar': round(100 * metric0(ref, hyp, uem=uem), 2),
                        'derCollar250ms': round(100 * metric25(ref, hyp, uem=uem), 2),
                        'runsMs': [round(r['inferenceMs']) for r in rows],
                        'sameOutputAllRuns': all(r['turns'] == rows[0]['turns'] for r in rows)}
    return out


def main():
    load = lambda n: json.loads((RESULTS / f'{n}.json').read_text()) if (RESULTS / f'{n}.json').exists() else None
    summary = {}
    if r := load('asr'):
        summary['asr'] = {'controlled': r['controlled'], 'conditions': [r['before'], r['after']], **asr_block(r['data'])}
    if r := load('clear'):
        d = r['data']
        rates = {row['reportedSampleRate'] for row in d['clear']['rows']}
        summary['clear'] = {'controlled': r['controlled'], 'requestedSampleRate': 16000,
                            'reportedSampleRates': sorted(rates), 'outputHeaders': d['outputHeaders'],
                            'medianMsPerFile': round(statistics.median(x['inferenceMs'] for x in d['clear']['rows'])),
                            **asr_block(d['noisy'], '-noisy'), **asr_block(d['noisyClear'], '-noisy+clear')}
    if r := load('ear'):
        rows = r['data']['rows']
        wrong = [x for x in rows if x['id'].split('-')[0] != x['language']]
        summary['ear'] = {'controlled': r['controlled'], 'files': len(rows),
                          'correct': len(rows) - len(wrong),
                          'wrongButReliable': [{'id': x['id'], 'got': x['language'], 'confidence': round(x['confidence'], 3)}
                                               for x in wrong if x['reliable']],
                          'medianMs': round(statistics.median(x['inferenceMs'] for x in rows))}
    if r := load('who'):
        summary['who'] = {'controlled': r['controlled'], 'firstLoadMs': round(r['data']['loadMs']),
                          'initiallyDownloaded': r['data']['initiallyDownloaded'], **der(r['data'])}
    (RESULTS / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
