"""Controls for the Clear-before-ASR result: does WER rise because of input level,
because of the noise, or because Clear changes speech itself? English set,
level-normalised to -23 dBFS RMS, Voz only. Writes results/clear-controls.json."""
import json
from pathlib import Path

import numpy as np
import soundfile as sf

import metrics
import run

ROOT = run.ROOT
TARGET_RMS = 10 ** (-23 / 20)
OUT = ROOT / 'data' / 'clear_controls'


def main():
    before = run.conditions()
    clean = [m for m in run.MANIFEST if m['lang'] == 'en' and 'condition' not in m]
    rng = np.random.default_rng(7)
    sets = {}
    for name, snr in [('clean', None), ('snr15', 15), ('snr5', 5)]:
        folder = OUT / name
        (folder / 'clear').mkdir(parents=True, exist_ok=True)
        items = []
        for m in clean:
            audio, rate = sf.read(m['file'], dtype='float32')
            audio = audio * (TARGET_RMS / np.sqrt(np.mean(audio ** 2)))
            if snr is not None:
                noise = rng.standard_normal(len(audio)).astype('float32')
                audio = audio + noise * np.sqrt(np.mean(audio ** 2) / (np.mean(noise ** 2) * 10 ** (snr / 10)))
            path = folder / Path(m['file']).name
            sf.write(path, np.clip(audio, -1, 1), rate, subtype='PCM_16')
            items.append({'id': m['id'], 'file': str(path), 'output': str(folder / 'clear' / path.name)})
        run.bench('clear', items, 1)
        for variant, key in [('raw', 'file'), ('clear', 'output')]:
            voz = run.bench('voz', [{'id': i['id'], 'file': i[key]} for i in items], 1)
            pairs = [(run.MANIFEST_BY_ID[r['id']]['reference'], r['text']) for r in voz['rows']]
            sets[f'{name}-{variant}'] = {'werVoz': metrics.wer(pairs), 'files': len(pairs)}
    record = {'stage': 'clear-controls', 'levelDbfsRms': -23, 'before': before, 'after': run.conditions(), 'sets': sets}
    (run.RESULTS / 'clear-controls.json').write_text(json.dumps(record, indent=1))
    print(json.dumps(sets, indent=1))


if __name__ == '__main__':
    main()
