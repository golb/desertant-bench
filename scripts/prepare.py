"""Build the public test set: 100 FLEURS sentences per language (one recording
per sentence, lowest sentence ids first) and noisy copies of the English set."""
import csv
import json
import tarfile
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
FLEURS = ROOT / 'data' / 'fleurs'
LANGS = {'en_us': 'en', 'ru_ru': 'ru', 'es_419': 'es'}
PER_LANG = 100
SNR_DB = 5
csv.field_size_limit(1 << 24)


def pick(tsv):
    first = {}
    with open(tsv, newline='') as f:
        for row in csv.reader(f, delimiter='\t', quoting=csv.QUOTE_NONE):
            first.setdefault(int(row[0]), row)
    return [first[k] for k in sorted(first)[:PER_LANG]]


def main():
    manifest = []
    for code, lang in LANGS.items():
        rows = pick(FLEURS / f'{code}.test.tsv')
        wanted = {r[1] for r in rows}
        out = FLEURS / code
        out.mkdir(exist_ok=True)
        with tarfile.open(FLEURS / f'{code}.test.tar.gz') as tar:
            for member in tar:
                name = Path(member.name).name
                if member.isfile() and name in wanted:
                    (out / name).write_bytes(tar.extractfile(member).read())
        for r in rows:
            path = out / r[1]
            if not path.exists():
                raise SystemExit(f'missing {path}')
            manifest.append({'id': f'{lang}-{r[0]}', 'lang': lang, 'file': str(path),
                             'seconds': sf.info(path).duration, 'reference': r[2]})

    # Noisy English copies: seeded white noise at a fixed SNR, so Clear has
    # something to remove and the run is reproducible.
    rng = np.random.default_rng(7)
    noisy = FLEURS / 'en_us_noisy'
    noisy.mkdir(exist_ok=True)
    for item in [m for m in manifest if m['lang'] == 'en']:
        audio, rate = sf.read(item['file'], dtype='float32')
        noise = rng.standard_normal(len(audio)).astype('float32')
        scale = np.sqrt(np.mean(audio ** 2) / (np.mean(noise ** 2) * 10 ** (SNR_DB / 10)))
        mixed = np.clip(audio + scale * noise, -1, 1)
        path = noisy / Path(item['file']).name
        sf.write(path, mixed, rate, subtype='PCM_16')
        manifest.append({**item, 'id': item['id'] + '-noisy', 'lang': 'en', 'file': str(path),
                         'condition': f'white_noise_snr_{SNR_DB}db'})

    (ROOT / 'data' / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print(len(manifest), 'items')


if __name__ == '__main__':
    main()
