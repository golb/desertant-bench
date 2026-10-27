"""Speed on continuous audio: the 60 s AMI excerpt from demo/, 3 fresh processes
per engine, alternating. FLEURS clips are ~10 s and Whisper pads every input to a
30 s window, so the FLEURS ratio overstates the gap; this is the fair number.
Writes results/continuous.json."""
import json
import re
import statistics
import subprocess
import time

import run

AUDIO = run.ROOT / 'demo' / 'ami-ES2004a-5m00-60s.wav'


def whisper_once():
    tick = time.perf_counter()
    out = subprocess.run(['whisper-cli', '-m', str(run.WHISPER_MODEL), '-l', 'en', '-t', '8', '-nt', '-f', str(AUDIO)],
                         capture_output=True, text=True, check=True)
    wall = (time.perf_counter() - tick) * 1000
    load = float(re.search(r'load time =\s+([\d.]+) ms', out.stderr)[1])
    return {'callMs': wall, 'loadMs': load, 'inferenceMs': wall - load}


def voz_once():
    tick = time.perf_counter()
    r = run.bench('voz', [{'id': 'ami', 'file': str(AUDIO)}], 1)
    return {'callMs': (time.perf_counter() - tick) * 1000, 'loadMs': r['loadMs'], 'inferenceMs': r['rows'][0]['callMs']}


def main():
    run.cooldown()
    before = run.conditions()
    runs = {'whisper': [], 'voz': []}
    for _ in range(3):
        runs['whisper'].append(whisper_once())
        runs['voz'].append(voz_once())
    med = {e: {k: round(statistics.median(r[k] for r in rs)) for k in ('callMs', 'loadMs', 'inferenceMs')} for e, rs in runs.items()}
    record = {'stage': 'continuous', 'audio': 'AMI ES2004a 300-360 s, 16 kHz mono', 'before': before, 'after': run.conditions(),
              'controlled': run.controlled(before, run.conditions()), 'median': med,
              'speedupCall': round(med['whisper']['callMs'] / med['voz']['callMs'], 1),
              'speedupInference': round(med['whisper']['inferenceMs'] / med['voz']['inferenceMs'], 1), 'runs': runs}
    (run.RESULTS / 'continuous.json').write_text(json.dumps(record, indent=1))
    print(json.dumps({k: record[k] for k in ('controlled', 'median', 'speedupCall', 'speedupInference')}, indent=1))


if __name__ == '__main__':
    main()
