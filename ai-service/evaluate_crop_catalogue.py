"""Real-image coverage check for all enabled model classes; NOT independent accuracy."""
import csv
import hashlib
import json
import random
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import main

REVISION = '7f7ecc7e1eaca78107e3affe7cb5abd9427e139a'
REPO = 'spMohanty/PlantVillage-Dataset'
CACHE = main.BASE_DIR / '.model-cache/crop-catalogue'
OUT = main.BASE_DIR / 'evaluation/crop-catalogue'


def fetch(url):
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'CropCatalogueEvaluation/1.0'})
            with urllib.request.urlopen(request, timeout=40) as response:
                data = response.read(8_000_001)
                if len(data) > 8_000_000:
                    raise ValueError('Download exceeded the size limit')
                return data
        except OSError:
            if attempt == 2:
                raise


def tree(sha):
    path = CACHE / f'tree-{sha}.json'
    old_cache = main.BASE_DIR / '.model-cache/training-pilot' / path.name
    if not path.exists():
        path.write_bytes(old_cache.read_bytes() if old_cache.exists() else fetch(f'https://api.github.com/repos/{REPO}/git/trees/{sha}'))
    data = json.loads(path.read_text())
    if data.get('truncated') or data.get('sha') != sha:
        raise ValueError('Dataset metadata is truncated or does not match its pinned revision')
    return data['tree']


def run():
    CACHE.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'status.json').write_text(json.dumps({'status': 'running'}))
    entries = tree(REVISION)
    for directory in ['raw', 'color']:
        entries = tree(next(item['sha'] for item in entries if item['path'] == directory))
    classes = {item['path']: item for item in entries}
    samples = []
    for crop, spec in main.CROPS.items():
        for label in spec['classes']:
            files = [item for item in tree(classes[label]['sha']) if item['type'] == 'blob' and item['path'].lower().endswith(('.jpg', '.jpeg', '.png')) and item.get('size', 0) <= main.MAX_BYTES]
            random.Random('catalogue-20261123:' + label).shuffle(files := sorted(files, key=lambda item: item['path']))
            if len(files) < 3:
                raise ValueError(f'Not enough real images for {label}')
            for item in files[:3]:
                source = f'raw/color/{label}/{item["path"]}'
                samples.append({'crop': crop, 'expected_label': label, 'source_path': source,
                                'git_blob_sha': item['sha'],
                                'url': f'https://raw.githubusercontent.com/{REPO}/{REVISION}/' + urllib.parse.quote(source)})
    def download(sample):
        path = CACHE / (hashlib.sha256(sample['source_path'].encode()).hexdigest()[:24] + Path(sample['source_path']).suffix.lower())
        if not path.exists():
            raw = fetch(sample['url'])
            temporary = path.with_suffix('.part')
            temporary.write_bytes(raw)
            temporary.replace(path)
        raw = path.read_bytes()
        if hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() != sample['git_blob_sha']:
            raise ValueError('Dataset image checksum mismatch')
        return sample, path, raw
    with ThreadPoolExecutor(max_workers=6) as pool:
        downloaded = list(pool.map(download, samples))
    import torch
    torch.set_num_threads(2)
    main.get_classifier()
    rows = []
    for sample, path, raw in downloaded:
        result = main.classify(raw, sample['crop'])
        if any(item['label'] not in main.CROPS[sample['crop']]['classes'] for item in result['top_predictions']):
            raise ValueError('A prediction escaped its selected crop classes')
        if main.CROPS[sample['crop']]['coverage'] != 'healthy_and_diseases' and not result['uncertain']:
            raise ValueError('Limited-coverage crop incorrectly presented as a confident diagnosis')
        rows.append({**sample, 'sha256': hashlib.sha256(raw).hexdigest(),
                     'predicted_label': result['label'], 'confidence': result['confidence'],
                     'correct': result['label'] == sample['expected_label'],
                     'uncertain': result['uncertain'], 'limited_coverage': result['limited_coverage']})
    summary = {}
    for crop, spec in main.CROPS.items():
        selected = [row for row in rows if row['crop'] == crop]
        summary[crop] = {'label': spec['label'], 'class_count': len(spec['classes']), 'coverage': spec['coverage'],
                         'tested': len(selected), 'correct': sum(row['correct'] for row in selected),
                         'uncertain': sum(row['uncertain'] for row in selected)}
        print(f'{spec["label"]}: {summary[crop]["correct"]}/{len(selected)}; coverage={spec["coverage"]}', flush=True)
    report = {'model': main.MODEL_ID, 'revision': main.MODEL_REVISION,
              'dataset': REPO, 'dataset_revision': REVISION, 'images': len(rows),
              'correct': sum(row['correct'] for row in rows), 'by_crop': summary,
              'purpose': 'Real-image preprocessing/routing/label coverage verification, not independent field accuracy.',
              'overlap': 'PlantVillage was used to train this pretrained model. Exact images may have been seen. Source photos are laboratory-style and do not establish field performance.',
              'limited_class_caution': 'A correct match for a single-class crop is not disease-detection accuracy; crop-restricted ranking has only one possible result.',
              'training': 'No model weights were trained or changed by this expansion.'}
    (OUT / 'report.json').write_text(json.dumps(report, indent=2))
    with (OUT / 'predictions.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    (OUT / 'status.json').write_text(json.dumps({'status': 'completed', 'images': len(rows)}))
    print(f'Completed {len(rows)} real-image checks across {len(summary)} crops. This is not independent accuracy verification.', flush=True)


if __name__ == '__main__':
    try:
        run()
    except Exception as exc:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / 'status.json').write_text(json.dumps({'status': 'failed', 'error': f'{type(exc).__name__}: {exc}'}))
        raise
