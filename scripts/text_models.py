"""Title (MLX) and Toxic (ONNX) worker for the public benchmark. Adapted from the Anna integration."""
import argparse
import json
import os
from pathlib import Path
import time

REVISIONS = {
    'title': '0a7c63976754b2e2af23c9f835218fb88e122dbe',
    'toxic': '3553f77942789ade867a462387bc2dbf8e92743f',
}

def download(root):
    from huggingface_hub import snapshot_download
    for name, revision in REVISIONS.items():
        patterns = (['*.json', '*.jinja', '*.safetensors', 'README.md', 'THIRD_PARTY_NOTICES.md']
                    if name == 'title' else ['toxic.onnx', 'tokenizer.json', 'tokenizer_config.json', 'toxic_meta.json', 'labels.json', 'README.md', 'THIRD_PARTY_NOTICES.md'])
        snapshot_download('desert-ant-labs/' + name, revision=revision,
                          local_dir=root / name, allow_patterns=patterns)
        print(name, revision, flush=True)

def card(raw):
    title, description = '', ''
    for line in raw.splitlines():
        line = line.strip()
        if line.upper().startswith('TITLE:'):
            title = line[6:].strip()
        elif line.upper().startswith('DESCRIPTION:'):
            description = line[12:].strip()
        elif line.upper().startswith('DESC:'):
            description = line[5:].strip()
        elif not title and line:
            title = line
    return {'title': title, 'description': description, 'raw': raw}

def run(request):
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    name = request['model']
    if name not in REVISIONS:
        raise ValueError('unsupported_model')
    directory = Path(request['modelRoot']) / name
    start = time.perf_counter()
    if name == 'title':
        from mlx_lm import load, stream_generate
        from mlx_lm.sample_utils import make_sampler
        model, tokenizer = load(str(directory))
        def predict(item):
            prompt = ('Write a factual title (3-8 words) and a 1-2 sentence description for this passage.'
                      'Be specific enough to identify this passage. No emoji, no hashtags, no hype.'
                      'Write in the same language as the passage.\n\nPASSAGE:\n' + item['text'])
            prompt = tokenizer.apply_chat_template([{'role': 'user', 'content': prompt}],
                                                    tokenize=False, add_generation_prompt=True)
            text, last = '', None
            for response in stream_generate(model, tokenizer, prompt, max_tokens=128, sampler=make_sampler(temp=0)):
                text += response.text
                last = response
            if last is None:
                raise ValueError('title_empty_generation')
            return {**card(text), 'promptTokens': last.prompt_tokens,
                    'generationTokens': last.generation_tokens, 'tokenLimit': 128,
                    'hitTokenLimit': last.generation_tokens >= 128}
        backend = 'mlx-gpu-python'
    else:
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
        meta = json.loads((directory / 'toxic_meta.json').read_text())
        tokenizer = Tokenizer.from_file(str(directory / 'tokenizer.json'))
        session_options = ort.SessionOptions()
        session_options.intra_op_num_threads = 4
        session = ort.InferenceSession(str(directory / 'toxic.onnx'), sess_options=session_options,
                                       providers=['CPUExecutionProvider'])
        def predict(item):
            # Tokenizer owns special tokens; 128 is the shipped model's input.
            tokenizer.no_truncation()
            full = tokenizer.encode(item['text'])
            tokenizer.enable_truncation(max_length=128)
            encoded = tokenizer.encode(item['text'])
            pad = tokenizer.token_to_id('<pad>')
            ids = encoded.ids + [pad] * (128 - len(encoded.ids))
            mask = [1] * len(encoded.ids) + [0] * (128 - len(encoded.ids))
            arrays = {'input_ids': ids, 'attention_mask': mask}
            inputs = {spec.name: np.array([arrays[spec.name]], dtype=np.int64 if spec.type == 'tensor(int64)' else np.int32)
                      for spec in session.get_inputs()}
            values = dict(zip([spec.name for spec in session.get_outputs()], session.run(None, inputs)))
            logits = np.asarray(values['content_logits']).reshape(-1)
            scores = 1 / (1 + np.exp(-np.clip(logits, -80, 80)))
            scores = {label: float(value) for label, value in zip(meta['content_labels'], scores)}
            thresholds = {label: meta['content_thresholds'][label]['default'] for label in scores}
            return {'scores': scores, 'thresholds': thresholds,
                    'flags': {key: value >= thresholds[key] for key, value in scores.items()},
                    'languageSupported': item['language'] in meta['languages'],
                    'inputTokens': len(encoded.ids), 'originalTokens': len(full.ids), 'truncated': len(full.ids) > 128,
                    'disabledHeads': meta.get('disabled_heads', [])}
        backend = 'onnxruntime-cpu-4threads'
    load_ms = (time.perf_counter() - start) * 1000
    rows = []
    passes = request.get("passes", 1)
    if not isinstance(passes, int) or passes < 1 or passes > 10:
        raise ValueError('invalid_passes')
    for item in request['inputs']:
        for repeat in range(passes):
            tick = time.perf_counter()
            result = predict(item)
            rows.append({'id': item['id'], 'repeat': repeat,
                         'inferenceMs': (time.perf_counter() - tick) * 1000, **result})
    from importlib.metadata import version
    return {'model': name, 'revision': REVISIONS[name], 'backend': backend, 'loadMs': load_ms,
            'rows': rows, 'versions': {key: version(key) for key in ['mlx-lm', 'mlx', 'onnxruntime', 'tokenizers']}}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('request', nargs='?')
    parser.add_argument('--download', type=Path)
    args = parser.parse_args()
    if args.download:
        download(args.download)
    else:
        request = json.loads(Path(args.request).read_text())
        print(json.dumps(run(request), ensure_ascii=False))
