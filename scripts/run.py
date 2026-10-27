"""Run the public benchmark. Usage: uv run python scripts/run.py STAGE [--passes N]
Stages: asr, clear, ear, who, text, all. Each writes results/<stage>.json with
the machine conditions captured before and after, so a run made on battery or
under load is marked as such instead of looking clean."""
import argparse
import json
import platform
import re
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / 'native' / '.build' / 'release' / 'bench'
CACHE = ROOT / 'cache'
WHISPER_MODEL = ROOT / 'models' / 'ggml-whisper-large-v3.bin'
RESULTS = ROOT / 'results'
MANIFEST = json.loads((ROOT / 'data' / 'manifest.json').read_text())
MANIFEST_BY_ID = {m["id"]: m for m in MANIFEST}
CONTROLS = json.loads((ROOT / 'data' / 'controls.json').read_text())


def sh(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()


def conditions():
    batt = sh('pmset', '-g', 'batt')
    return {'at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
            'power': 'ac' if "AC Power" in batt else 'battery',
            'battery': (re.search(r'(\d+)%', batt) or [None, None])[1],
            'loadAverage': [float(x) for x in sh('sysctl', '-n', 'vm.loadavg').strip('{} ').split()],
            'cpuIdlePercent': float(re.findall(r'([\d.]+)% idle', sh('top', '-l', '2', '-n', '0', '-s', '1'))[-1]),
            'thermal': sh('pmset', '-g', 'therm')}


# macOS load average counts waiting threads and sits at 4-5 on an idle
# desktop, so the gate uses CPU idle share from `top` instead.
IDLE_MIN = 85.0


def cooldown(max_wait=600):
    """Wait until the CPU is mostly idle, so each stage starts on a quiet
    machine rather than in the tail of the previous one."""
    start = time.time()
    while conditions()['cpuIdlePercent'] < IDLE_MIN and time.time() - start < max_wait:
        time.sleep(10)
    return round(time.time() - start)


def controlled(before, after):
    # The after-load includes this stage's own work, so only power is checked after.
    # ponytail: coarse gate (power + idle share before the stage); sample during the run if this proves too loose
    return before['power'] == 'ac' and after['power'] == 'ac' and before['cpuIdlePercent'] >= IDLE_MIN


def bench(model, inputs, passes):
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
        json.dump({'model': model, 'cacheRoot': str(CACHE), 'inputs': inputs, 'passes': passes}, f)
    out = subprocess.run([str(BENCH), f.name], capture_output=True, text=True)
    if out.returncode:
        raise SystemExit(out.stderr)
    return json.loads(out.stdout)


def whisper(items, lang):
    """One whisper-cli process for the whole set: the model loads once, like Voz."""
    args = ['whisper-cli', '-m', str(WHISPER_MODEL), '-l', lang, '-t', '8', '-nt', '-otxt']
    for item in items:
        args += ['-f', item['file']]
    tick = time.perf_counter()
    out = subprocess.run(args, capture_output=True, text=True)
    wall = (time.perf_counter() - tick) * 1000
    if out.returncode:
        raise SystemExit(out.stderr[-2000:])
    load = float(re.search(r'load time =\s+([\d.]+) ms', out.stderr)[1])
    texts = {}
    for item in items:
        txt = Path(item['file'] + '.txt')
        texts[item['id']] = txt.read_text().strip()
        txt.unlink()
    return {'model': 'whisper.cpp 1.9.1 / large-v3', 'loadMs': load, 'wallMs': wall, 'texts': texts}


def stage_asr(passes, items=None, tag='asr'):
    langs = {}
    for lang in ['en', 'ru', 'es']:
        subset = items or [m for m in MANIFEST if m['lang'] == lang and 'condition' not in m]
        subset = [m for m in subset if m['lang'] == lang]
        if not subset:
            continue
        voz = bench('voz', [{'id': m['id'], 'file': m['file']} for m in subset], passes)
        langs[lang] = {'audioSeconds': sum(m['seconds'] for m in subset), 'voz': voz,
                       'whisper': whisper(subset, lang)}
    return langs


def stage_clear(passes):
    noisy = [m for m in MANIFEST if m.get('condition')]
    out = ROOT / 'data' / 'fleurs' / 'en_us_noisy_clear'
    out.mkdir(exist_ok=True)
    clear = bench('clear', [{'id': m['id'], 'file': m['file'], 'output': str(out / Path(m['file']).name)}
                            for m in noisy], passes)
    cleaned = [{**m, 'id': m['id'] + '-clear', 'file': str(out / Path(m['file']).name)} for m in noisy]
    files = sorted(out.glob('*.wav'))[:3]
    headers = {f.name: sh('afinfo', str(f)).split('Data format:')[1].split('\n')[0].strip() for f in files}
    return {'clear': clear, 'outputHeaders': headers,
            'noisy': stage_asr(1, noisy), 'noisyClear': stage_asr(1, cleaned)}


def stage_ear(passes):
    clean = [m for m in MANIFEST if 'condition' not in m]
    return bench('ear', [{'id': m['id'], 'file': m['file']} for m in clean], passes)


def stage_who(passes):
    meetings = ['ES2004a', 'IS1009a']
    return bench('who', [{'id': m, 'file': str(ROOT / 'data' / 'ami' / f'{m}.wav')} for m in meetings], passes)


def stage_text(passes):
    gist = bench('gist', [{'id': c['id'], 'text': c['text']} for c in CONTROLS if 'gist' in c['tasks']], passes)
    worker = {}
    for model in ['title', 'toxic']:
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
            json.dump({'model': model, 'modelRoot': str(CACHE / 'hf'), 'passes': passes,
                       'inputs': [c for c in CONTROLS if model in c['tasks']]}, f)
        out = subprocess.run(['uv', 'run', 'python', str(ROOT / 'scripts' / 'text_models.py'), f.name],
                             capture_output=True, text=True, cwd=ROOT)
        if out.returncode:
            raise SystemExit(out.stderr[-2000:])
        worker[model] = json.loads(out.stdout)
    return {'gist': gist, **worker}


STAGES = {'asr': stage_asr, 'clear': stage_clear, 'ear': stage_ear, 'who': stage_who, 'text': stage_text}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=[*STAGES, 'all'])
    parser.add_argument('--passes', type=int, default=1)
    args = parser.parse_args()
    RESULTS.mkdir(exist_ok=True)
    for name in STAGES if args.stage == 'all' else [args.stage]:
        waited = cooldown()
        before = conditions()
        data = STAGES[name](args.passes)
        after = conditions()
        record = {'stage': name, 'passes': args.passes, 'sdk': '4.1.0',
                  'machine': {'chip': sh('sysctl', '-n', 'machdep.cpu.brand_string'),
                              'memoryBytes': int(sh('sysctl', '-n', 'hw.memsize')),
                              'os': platform.mac_ver()[0], 'arch': platform.machine()},
                  'cooldownSeconds': waited, 'before': before, 'after': after, 'controlled': controlled(before, after), 'data': data}
        (RESULTS / f'{name}.json').write_text(json.dumps(record, ensure_ascii=False, indent=1))
        print(name, 'controlled' if record['controlled'] else 'NOT CONTROLLED (battery or load)', flush=True)
