"""Evaluate 40 labeled maize field photos using the application's real classifier.

No extra dependencies: run with .venv/Scripts/python.exe evaluate_maize.py.
Images stay in ignored .model-cache; reports and a reproducible manifest are small.
"""
import collections
import csv
import hashlib
import io
import json
import math
import platform
import random
import sys
import time
import traceback
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone
from importlib.metadata import version
from pathlib import Path

import main
from PIL import Image, ImageOps
from huggingface_hub import hf_hub_download

ROOT = main.BASE_DIR.parent
CACHE = main.BASE_DIR / '.model-cache/maize-evaluation'
MANIFEST = main.BASE_DIR / 'evaluation/maize-manifest.json'
DOCS = ROOT / 'docs'
SEED = 20261116
MODEL_REVISION = '77e6d262dca53b818f7ad1d67088700754515639'
ARTICLE_API = 'https://api.figshare.com/v2/articles/20237613/versions/1'
DOI = 'https://doi.org/10.25403/UPresearchdata.20237613.v1'
FLAGS = ['GLS', 'NCLB', 'PLS', 'CR', 'SR', 'NoFoliarSymptoms', 'Other', 'UnidentifiedDisease']
CLASSES = {
    'NoFoliarSymptoms': ('Healthy', 'Corn_(maize)___healthy'),
    'CR': ('Common rust', 'Corn_(maize)___Common_rust_'),
    'NCLB': ('Northern leaf blight', 'Corn_(maize)___Northern_Leaf_Blight'),
    'GLS': ('Gray leaf spot', 'Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot'),
}
LABELS = [value[1] for value in CLASSES.values()]
NAMES = [value[0] for value in CLASSES.values()]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def fetch(url, limit, headers=None):
    """Bounded download; retries never replace a sample or a prediction."""
    for attempt in range(3):
        try:
            started = time.monotonic()
            request = urllib.request.Request(url, headers={'User-Agent': 'CropDiseaseEvaluation/1.0', **(headers or {})})
            with urllib.request.urlopen(request, timeout=30) as response:
                if headers and 'Range' in headers and response.status != 206:
                    raise RuntimeError('Server ignored a required byte range')
                pieces, received = [], 0
                while True:
                    if time.monotonic() - started > 60:
                        raise TimeoutError('Download exceeded the 60-second attempt deadline')
                    chunk = response.read(min(65536, limit + 1 - received))
                    if not chunk:
                        break
                    pieces.append(chunk)
                    received += len(chunk)
                    if received > limit:
                        raise ValueError(f'Download exceeded byte limit: {url}')
                data = b''.join(pieces)
                if len(data) > limit:
                    raise ValueError(f'Download exceeded byte limit: {url}')
                return data, response.status, dict(response.headers)
        except Exception as exc:
            print(f'Download attempt {attempt + 1}/3 failed: {type(exc).__name__}: {exc}', flush=True)
            if attempt == 2:
                raise
            time.sleep(1 + attempt)


def json_file(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


class RangeArchive(io.RawIOBase):
    """Seekable ZIP source: downloads selected entries, not the 10.8 GB archive."""
    def __init__(self, url, size):
        self.url, self.size, self.position = url, size, 0
        self.buffer_start, self.buffer = -1, b''
        self.downloaded = 0

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        self.position = offset if whence == 0 else self.position + offset if whence == 1 else self.size + offset
        if self.position < 0:
            raise ValueError('Negative archive seek')
        return self.position

    def read(self, size=-1):
        size = self.size - self.position if size < 0 else min(size, self.size - self.position)
        if size <= 0:
            return b''
        offset = self.position - self.buffer_start
        if offset < 0 or offset + size > len(self.buffer):
            end = min(self.size, self.position + max(size, 65536)) - 1
            url = self.url + f'?evaluation_range={self.position}-{end}'
            data, status, headers = fetch(url, end - self.position + 1, {'Range': f'bytes={self.position}-{end}'})
            content_range = next((v for k, v in headers.items() if k.lower() == 'content-range'), '')
            if status != 206 or content_range != f'bytes {self.position}-{end}/{self.size}':
                raise RuntimeError('Server did not honor the archive range; refusing a full archive download')
            if len(data) != end - self.position + 1:
                raise RuntimeError('Truncated ZIP range')
            self.downloaded += len(data)
            self.buffer_start, self.buffer, offset = self.position, data, 0
        data = self.buffer[offset:offset + size]
        self.position += len(data)
        return data


def metadata():
    raw, _, _ = fetch(ARTICLE_API, 1_000_000)
    article = json.loads(raw)
    if article['version'] != 1 or article['doi'] != '10.25403/UPresearchdata.20237613.v1':
        raise ValueError('Unexpected dataset version')
    files = {entry['name']: entry for entry in article['files']}
    labels, _, _ = fetch(files['Database.csv']['download_url'], 1_000_000)
    readme, _, _ = fetch(files['ReadMe.txt']['download_url'], 100_000)
    for name, content in [('Database.csv', labels), ('ReadMe.txt', readme)]:
        if hashlib.md5(content).hexdigest() != files[name]['computed_md5']:
            raise ValueError(f'Dataset metadata checksum mismatch: {name}')
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / 'Database.csv').write_bytes(labels)
    (CACHE / 'ReadMe.txt').write_bytes(readme)
    json_file(CACHE / 'article.json', article)
    return article, files, labels, readme


def image_details(data):
    with Image.open(io.BytesIO(data)) as source:
        width, height = source.size
        if source.format != 'JPEG':
            raise ValueError('Dataset image is not a JPEG')
        source.verify()
    with Image.open(io.BytesIO(data)) as source:
        pixels = ImageOps.exif_transpose(source).convert('RGB')
        pixel_hash = sha256(str(pixels.size).encode() + pixels.tobytes())
    return width, height, pixel_hash


def prepare():
    article, files, raw_labels, readme = metadata()
    rows = list(csv.DictReader(io.StringIO(raw_labels.decode('utf-8-sig'))))
    if len({row['filePath'] for row in rows}) != len(rows):
        raise ValueError('Duplicate label filenames require manual review')
    archive = RangeArchive(files['leaf_images.zip']['download_url'], files['leaf_images.zip']['size'])
    exclusions, samples, eligibility = [], [], {}
    seen_bytes, seen_pixels = set(), set()
    with zipfile.ZipFile(archive) as source:
        entries = {}
        for entry in source.infolist():
            if entry.is_dir():
                continue
            basename = Path(entry.filename).name
            if basename in entries:
                raise ValueError('Ambiguous archive basename')
            entries[basename] = entry
        for flag, (name, label) in CLASSES.items():
            single = [row for row in rows if row[flag] == '1' and sum(int(row[key]) for key in FLAGS) == 1]
            candidates = [row for row in single if row['filePath'] in entries and entries[row['filePath']].file_size <= main.MAX_BYTES]
            eligibility[flag] = {'single_label': len(single), 'under_5_mib': len(candidates)}
            candidates.sort(key=lambda row: row['filePath'])
            random.Random(f'{SEED}:{flag}').shuffle(candidates)
            selected = 0
            for row in candidates:
                entry = entries[row['filePath']]
                cache_name = sha256(entry.filename.encode())[:20] + '.jpg'
                path = CACHE / cache_name
                if path.exists():
                    data = path.read_bytes()
                    # ZIP CRC independently checks cached bytes against the original entry.
                    import zlib
                    if len(data) != entry.file_size or zlib.crc32(data) != entry.CRC:
                        raise ValueError(f'Corrupt cached image: {cache_name}')
                else:
                    data = source.read(entry)  # zipfile validates CRC while extracting.
                    path.write_bytes(data)
                width, height, pixel_hash = image_details(data)
                digest = sha256(data)
                reason = 'over_20_megapixels' if width * height > main.MAX_PIXELS else 'duplicate' if digest in seen_bytes or pixel_hash in seen_pixels else None
                if reason:
                    exclusions.append({'filename': row['filePath'], 'reason': reason})
                    continue
                seen_bytes.add(digest)
                seen_pixels.add(pixel_hash)
                samples.append({'sample_id': f'{flag}-{selected + 1:02d}', 'dataset_image_id': row['imgID_id'],
                                'filename': row['filePath'], 'zip_member': entry.filename, 'cache_name': cache_name,
                                'source_flag': flag, 'expected_label': label, 'category': name,
                                'annotations': {key: int(row[key]) for key in FLAGS},
                                'sha256': digest, 'decoded_rgb_sha256': pixel_hash, 'bytes': len(data),
                                'width': width, 'height': height, 'zip_crc32': entry.CRC})
                selected += 1
                print(f'Downloaded {len(samples)}/40: {name}: {row["filePath"]}', flush=True)
                if selected == 10:
                    break
            if selected != 10:
                raise RuntimeError(f'Insufficient eligible {name} images: {selected}/10')
    manifest = {'dataset': article['title'], 'doi': DOI, 'article_api': ARTICLE_API,
                'license': article['license'], 'author': 'Hamish Craze', 'seed': SEED,
                'selection': 'Seeded shuffle of sorted single-label original filenames, 10/class; upload-size/pixel/duplicate exclusions before inference',
                'label_csv_sha256': sha256(raw_labels), 'readme_sha256': sha256(readme),
                'archive': files['leaf_images.zip'], 'eligible_pool': eligibility,
                'exclusions': exclusions, 'samples': samples}
    json_file(MANIFEST, manifest)
    print(f'Prepared 40 originals; transferred {archive.downloaded:,} archive bytes, without downloading the full archive.', flush=True)
    return manifest


def restore_images(manifest):
    missing = [s for s in manifest['samples'] if not (CACHE / s['cache_name']).exists()]
    if missing:
        archive = manifest['archive']
        with zipfile.ZipFile(RangeArchive(archive['download_url'], archive['size'])) as source:
            for sample in missing:
                data = source.read(sample['zip_member'])
                if sha256(data) != sample['sha256']:
                    raise ValueError('Source image no longer matches pinned manifest')
                (CACHE / sample['cache_name']).write_bytes(data)


def overlap_audit(manifest):
    splits = {}
    evidence = {}
    for name, revision in [('v1.0', '3a2cce39a518f6ae887fbbe01b6db35ad1209bf0'), ('v1.1', MODEL_REVISION)]:
        path = hf_hub_download(main.MODEL_ID, 'splits.json', revision=revision)
        raw = Path(path).read_bytes()
        data = json.loads(raw)
        splits[name] = {split: {Path(item[0]).name.casefold() for item in values} for split, values in data['splits'].items()}
        evidence[name] = {'revision': revision, 'splits_json_sha256': sha256(raw),
                          'split_sizes': {key: len(value) for key, value in splits[name].items()}}
    path = hf_hub_download(main.MODEL_ID, 'run_info.json', revision=MODEL_REVISION)
    run_info = json.loads(Path(path).read_bytes())
    commit = run_info['plantdoc_commit_pinned']
    url = f'https://api.github.com/repos/pratikkayal/PlantDoc-Dataset/git/trees/{commit}?recursive=1'
    raw, _, _ = fetch(url, 10_000_000)
    tree = json.loads(raw)
    if tree.get('truncated'):
        raise ValueError('Incomplete PlantDoc tree; cannot complete overlap audit')
    names = {Path(item['path']).name.casefold() for item in tree['tree'] if item['type'] == 'blob'}
    checks = []
    for sample in manifest['samples']:
        name = sample['filename'].casefold()
        checks.append({'sample_id': sample['sample_id'], 'filename': sample['filename'],
                       'plantvillage_matches': [f'{revision}/{split}' for revision, values in splits.items() for split, members in values.items() if name in members],
                       'plantdoc_filename_match': name in names})
    return {'method': 'Case-insensitive source basename comparison; not a byte/perceptual audit of all training images',
            'plantvillage': evidence, 'plantdoc_commit': commit, 'plantdoc_tree_sha256': sha256(raw),
            'plantdoc_tree_entries': len(tree['tree']), 'plantdoc_tree_url': url,
            'matches': [item for item in checks if item['plantvillage_matches'] or item['plantdoc_filename_match']],
            'checked_images': len(checks), 'checks': checks,
            'limitation': 'Pretoria is not a declared training source, but renamed/recompressed/web-reused images and undisclosed training sources cannot be excluded. Treat this as a preliminary external-dataset test, not certified independent accuracy.'}


def metrics(rows):
    matrix = [[0] * len(LABELS) for _ in LABELS]
    for row in rows:
        matrix[LABELS.index(row['expected_label'])][LABELS.index(row['predicted_label'])] += 1
    per_class = []
    for i, name in enumerate(NAMES):
        tp = matrix[i][i]
        support = sum(matrix[i])
        predicted = sum(row[i] for row in matrix)
        precision = tp / predicted if predicted else 0.0
        recall = tp / support if support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class.append({'category': name, 'label': LABELS[i], 'support': support, 'correct': tp,
                          'incorrect': support - tp, 'accuracy': recall, 'precision': precision, 'recall': recall, 'f1': f1})
    total = len(rows)
    correct = sum(matrix[i][i] for i in range(len(LABELS)))
    accuracy = correct / total
    z = 1.959963984540054
    center = (accuracy + z*z / (2*total)) / (1 + z*z/total)
    half = z * math.sqrt(accuracy*(1-accuracy)/total + z*z/(4*total*total)) / (1 + z*z/total)
    confident = [row for row in rows if not row['uncertain']]
    macro = {key: sum(c[key] for c in per_class) / len(per_class) for key in ['precision', 'recall', 'f1']}
    weighted = {key: sum(c[key]*c['support'] for c in per_class) / total for key in ['precision', 'recall', 'f1']}
    return {'total': total, 'correct': correct, 'incorrect': total-correct, 'accuracy': accuracy,
            'wilson_95_interval': [center-half, center+half], 'per_class': per_class,
            'macro': macro, 'weighted': weighted, 'micro': {key: accuracy for key in ['precision', 'recall', 'f1']},
            'confusion_matrix': matrix, 'class_order': NAMES,
            'uncertain': total-len(confident), 'confident': len(confident),
            'correct_confident': sum(row['correct'] for row in confident),
            'confident_accuracy': sum(row['correct'] for row in confident)/len(confident) if confident else None,
            'coverage': len(confident)/total, 'top3_correct': sum(row['top3_correct'] for row in rows)}


def write_report(result, manifest, audit):
    m = result['metrics']
    categories = '\n'.join(f"| {c['category']} | {c['support']} | {c['correct']} | {c['incorrect']} | {c['accuracy']:.1%} | {c['precision']:.3f} | {c['recall']:.3f} | {c['f1']:.3f} |" for c in m['per_class'])
    matrix = '\n'.join('| ' + name + ' | ' + ' | '.join(str(v) for v in row) + ' |' for name, row in zip(NAMES, m['confusion_matrix']))
    mapping = '\n'.join(f'| {flag} | {name} | `{label}` |' for flag, (name, label) in CLASSES.items())
    best = ', '.join(c['category'] for c in m['per_class'] if c['correct'] == max(x['correct'] for x in m['per_class']))
    worst = ', '.join(c['category'] for c in m['per_class'] if c['correct'] == min(x['correct'] for x in m['per_class']))
    accepted = f"{m['confident_accuracy']:.1%}" if m['confident_accuracy'] is not None else 'not defined (none accepted)'
    rust_index = NAMES.index('Common rust')
    rust_calls = sum(row[rust_index] for row in m['confusion_matrix'])
    rust_correct = m['confusion_matrix'][rust_index][rust_index]
    best_f1 = max(m['per_class'], key=lambda item: item['f1'])
    report = f'''# Maize disease evaluation: 40 real field photographs

**Preliminary external-dataset test. Not certified independent accuracy verification.**

Run date: {result['timestamp_lagos']} (Africa/Lagos). Status: **completed**, 40/40 images processed with real inference; zero download or inference failures in this completed run.

## Simple explanation

We tested **{m['total']} real maize photographs**, with 10 in each category. The model's highest-scoring maize class matched the dataset label for **{m['correct']} images** and was wrong for **{m['incorrect']} images**. That is **{m['accuracy']:.1%} top-1 accuracy** on these selected photos. Best category/categories: **{best}**. Lowest category/categories: **{worst}**.

The app would mark **{m['uncertain']} of 40** images as uncertain. It would show a confident result for **{m['confident']}**, of which **{m['correct_confident']}** were correct ({accepted} accuracy on accepted results; {m['coverage']:.1%} coverage). A top-ranked match below the app's threshold is counted in top-1 accuracy but is **not** a confirmed app answer. Correct-and-confident results cover {m['correct_confident']/m['total']:.1%} of all 40 images.

The model called **{rust_calls} photos Common rust**, but only **{rust_correct}** of those calls matched the dataset label. Its high common-rust hit rate therefore does not mean every rust prediction can be trusted. **{best_f1['category']}** had the strongest balance of precision and recall (F1 = {best_f1['f1']:.3f}). **{m['confident']-m['correct_confident']} of the {m['confident']} accepted/confident outputs were wrong.** This test does not support relying on the model alone for field diagnosis.

This small test describes these photographs only. It does not establish that the model is reliable for every farm, phone camera, disease stage or background. Ten images per category is a small sample: one mistake changes that category's result by 10 percentage points. A nominal 95% Wilson interval for overall top-1 accuracy is {m['wilson_95_interval'][0]:.1%} to {m['wilson_95_interval'][1]:.1%}; it assumes independent observations and does not account for correlated photos or label errors.

## Dataset selection and label mapping

We investigated [PlantVillage](https://github.com/spMohanty/PlantVillage-Dataset), which has all four requested categories. The deployed model's [training record](https://huggingface.co/{main.MODEL_ID}/blob/{MODEL_REVISION}/run_info.json) declares PlantVillage plus Cropped-PlantDoc. Using random PlantVillage images could therefore test training examples, and even its published test split is an in-domain evaluation. PlantDoc also belongs to the training source family and its public class directories do not include a healthy-maize category. The Mendeley [mixed-source corn collection](https://data.mendeley.com/datasets/hmkd6nbngr/1) combines field and public-repository images and does not establish independence; its generic blight label also needs clarification.

Instead, we selected original field photographs from **Hamish Craze, University of Pretoria, Diseases of maize in the field, version 1 (2022)**, DOI [{manifest['doi']}]({DOI}), licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The original dataset contains 2,355 maize field photos taken at different times and sites in South Africa. Provenance and annotations were retrieved from its [versioned API]({ARTICLE_API}), `Database.csv` and `ReadMe.txt`. Original photographs are used unchanged; no generated images or augmented copies are used.

| Source flag | Report category | Exact supported model label |
| --- | --- | --- |
{mapping}

`NoFoliarSymptoms` is mapped to Healthy because it means no recorded foliar disease symptoms; it is **not** a laboratory confirmation that a plant is free of pathogens. Gray/grey leaf spot is the same dataset category mapped to the model's combined Cercospora/gray leaf spot class. NCLB maps to Northern Leaf Blight. CR maps to Common Rust, never Southern Rust.

The source has multi-label rows. We require **exactly one of all eight annotation flags to be 1**, excluding mixed diseases, PLS, southern rust, Other and unidentified disease. We also require original JPEG size <= 5 MiB and resolution <= 20 megapixels, matching app limits. Files are sorted then shuffled with seed `{SEED}` and the category flag; the first 10 eligible unique images/class are selected **before inference**. No images are selected or replaced because of a favorable/unfavorable prediction. Selection is reproducible from [the manifest](../ai-service/evaluation/maize-manifest.json). Additional pixel-limit/duplicate exclusions after the file-size prefilter: {len(manifest['exclusions'])}. The manifest records the candidate counts before and after file-size filtering. The upload limits and single-label restriction make this a selected subset, not a random sample of all field photos.

Only selected ZIP entries are fetched through verified HTTP byte ranges; the 10.8 GB archive is not downloaded in full. ZIP CRC, source annotation-file checksums, image SHA-256 and decoded RGB hashes are checked. The 40 selected images have distinct byte hashes and distinct decoded RGB hashes. Near-duplicate leaves or multiple shots of the same plant cannot be excluded.

## Training-overlap investigation

The Pretoria collection is **not listed** among the model's declared PlantVillage/Cropped-PlantDoc training sources. We compared all {audit['checked_images']} selected source basenames, case-insensitively, with the **train, validation and test** filenames in both the base v1.0 and deployed v1.1 `splits.json`, and with every file in Cropped-PlantDoc at the exact commit `{audit['plantdoc_commit']}` declared by v1.1. Number of filename matches: **{len(audit['matches'])}**. Complete checks and metadata hashes are in [maize-overlap-audit.json](maize-overlap-audit.json).

This is a filename audit, **not** a full byte or perceptual comparison against every training image. Renamed, re-encoded or web-reused images, undocumented upstream sources, and related leaves cannot be ruled out. Thus this is a **preliminary external-dataset test with no detected filename overlap**, rather than proof that every image is independent. A stronger next evaluation should use newly collected, expert-labeled leaves, separate farms/dates/plants, more samples, and explicit image/plant-level deduplication against training data.

## Exactly what was tested

- Model: `{main.MODEL_ID}`, version `{main.MODEL_VERSION}`, immutable revision `{main.MODEL_REVISION}`.
- Called the **unchanged application's** `main.get_classifier()` once, then `main.classify(original_bytes, "maize")` for each photo. The main.py SHA-256 is `{result['main_py_sha256']}`. No duplicated inference pipeline, no mocked model, no tuning or retraining during this evaluation.
- The bundled processor converts the validated/EXIF-oriented image to RGB, resizes the short edge to 256, center-crops to 224x224, rescales by 1/255 and normalizes with mean/std 0.5.
- Publisher temperature `{result['temperature']}` is applied to logits before 38-class softmax. Predictions are ranked only among the four maize labels; full-model probabilities are retained, not normalized to artificially sum to 100% inside maize.
- The app marks scores below `{result['confidence_threshold']}` as uncertain. The top three maize classes and all four-category outcomes are recorded.
- This measures maize disease classification **given that maize was selected**. It does not evaluate automatic crop identification, unsupported disease rejection, non-leaf detection, or HTTP/browser reliability. Laravel's multipart field is `crop=maize`; its rendering does not change the class or confidence.
- Versions: Python {result['environment']['python']}, PyTorch {result['environment']['torch']}, Transformers {result['environment']['transformers']}, Pillow {result['environment']['pillow']}, NumPy {result['environment']['numpy']}.

## Results by category

| Actual category | Tested | Correct | Wrong | Category accuracy | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{categories}

Category accuracy is correct predictions divided by the 10 actual images in that class, which equals class recall here. Precision asks: of predictions calling a disease, how many were correct? Recall asks: of images labeled with that disease, how many did the model find? F1 balances precision and recall. Scores use the top-ranked maize class for **all** photos, including uncertain ones; zero denominators are defined as 0.

| Averaging | Precision | Recall | F1 |
| --- | ---: | ---: | ---: |
| Macro (equal weight per category) | {m['macro']['precision']:.3f} | {m['macro']['recall']:.3f} | {m['macro']['f1']:.3f} |
| Weighted (by actual class count) | {m['weighted']['precision']:.3f} | {m['weighted']['recall']:.3f} | {m['weighted']['f1']:.3f} |
| Micro (all decisions) | {m['micro']['precision']:.3f} | {m['micro']['recall']:.3f} | {m['micro']['f1']:.3f} |

Top-three recall: **{m['top3_correct']}/40 ({m['top3_correct']/40:.1%})**. This only means the dataset label was among three suggestions; it is not top-1 accuracy and does not mean the app gave a correct confident answer.

## Confusion matrix

Rows are the **actual dataset label**. Columns are the **predicted maize label**. The diagonal contains correct predictions; other cells show mistakes. All 40 decisions are included.

| Actual / Predicted | Healthy | Common rust | Northern leaf blight | Gray leaf spot |
| --- | ---: | ---: | ---: | ---: |
{matrix}

## Reproduce and inspect

From the existing Laravel project root, in PowerShell:

```powershell
ai-service/.venv/Scripts/python.exe ai-service/evaluate_maize.py
```

On first execution without the committed manifest, the script selects the fixed seeded sample and caches originals under ignored `ai-service/.model-cache/maize-evaluation/`. With the manifest present, it reuses exactly those images, downloads only missing originals and verifies their checksums. It checks the exact model revision and all four label IDs before inference. Reports are written only after 40 successful predictions. Errors exit nonzero and are recorded in `docs/maize-evaluation-status.json`; do not treat an old completed report as a successful new run after a failure. No global packages are installed. Nothing in Laravel or another mobile project is modified by the evaluation script.

- [Individual predictions CSV](maize-predictions.csv): all 40 source filenames, IDs, ground truth, predictions, confidence, uncertainty, top-three classes and hashes.
- [Metrics JSON](maize-metrics.json): exact numeric metrics, model/software provenance and status.
- [Confusion matrix CSV](maize-confusion-matrix.csv).
- [Source/selection manifest](../ai-service/evaluation/maize-manifest.json): labels, dataset IDs, ZIP members, annotation flags and hashes; images are deliberately not committed.
- [Overlap audit](maize-overlap-audit.json).

**Can we trust it?** We can trust this as a recorded, reproducible result for these 40 source-labeled photos under the current application pipeline. We still need larger, expert-verified, plant-separated independent testing before claiming general real-world accuracy. Confidence percentages are model scores, not guarantees that a diagnosis is correct.
'''
    (DOCS / 'model-evaluation.md').write_text(report, encoding='utf-8')


def run():
    CACHE.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)
    if main.MODEL_REVISION != MODEL_REVISION:
        raise ValueError('The app model revision changed; explicitly review the evaluation before rerunning')
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8')) if MANIFEST.exists() else prepare()
    samples = manifest['samples']
    counts = collections.Counter(sample['expected_label'] for sample in samples)
    if len(samples) != 40 or counts != collections.Counter({label: 10 for label in LABELS}):
        raise ValueError('Manifest must contain exactly 10 images per supported maize category')
    if len({s['sha256'] for s in samples}) != 40 or len({s['decoded_rgb_sha256'] for s in samples}) != 40:
        raise ValueError('Duplicate evaluation images')
    restore_images(manifest)
    audit = overlap_audit(manifest)
    if audit['matches']:
        raise ValueError('Detected potential training overlap; review samples before evaluation')
    print('Overlap audit: 40 checked; no declared-source filename matches.', flush=True)
    model = main.get_classifier()
    supported = {label for label in model.config.id2label.values() if label.startswith(main.CROP_PREFIXES['maize'])}
    if supported != set(LABELS):
        raise ValueError('Dataset labels do not exactly match the model maize classes')
    rows = []
    for index, sample in enumerate(samples, 1):
        data = (CACHE / sample['cache_name']).read_bytes()
        width, height, pixel_hash = image_details(data)
        if len(data) != sample['bytes'] or sha256(data) != sample['sha256'] or pixel_hash != sample['decoded_rgb_sha256']:
            raise ValueError(f'Image checksum mismatch: {sample["sample_id"]}')
        if len(data) > main.MAX_BYTES or width*height > main.MAX_PIXELS:
            raise ValueError('Sample exceeds application upload limits')
        prediction = main.classify(data, 'maize')
        if prediction['revision'] != MODEL_REVISION or prediction['label'] not in LABELS:
            raise ValueError('Unexpected model/prediction')
        row = {'sample_id': sample['sample_id'], 'dataset_image_id': sample['dataset_image_id'],
               'source_filename': sample['filename'], 'source_zip_member': sample['zip_member'],
               'expected_label': sample['expected_label'], 'predicted_label': prediction['label'],
               'correct': prediction['label'] == sample['expected_label'], 'confidence': prediction['confidence'],
               'uncertain': prediction['uncertain'], 'uncertainty_reason': prediction['uncertainty_reason'],
               'selected_crop_confidence': prediction['selected_crop_confidence'],
               'top3_correct': sample['expected_label'] in [p['label'] for p in prediction['top_predictions']],
               'sha256': sample['sha256'], 'decoded_rgb_sha256': pixel_hash, 'bytes': len(data), 'width': width, 'height': height}
        for rank, item in enumerate(prediction['top_predictions'], 1):
            row[f'top{rank}_label'], row[f'top{rank}_confidence'] = item['label'], item['confidence']
        rows.append(row)
        print(f'{index}/40 {sample["category"]}: {"correct" if row["correct"] else "WRONG"}, score={row["confidence"]:.4f}, uncertain={row["uncertain"]}', flush=True)
    result = {'status': 'completed', 'timestamp_lagos': datetime.now(timezone(timedelta(hours=1), 'Africa/Lagos')).isoformat(),
              'model': main.MODEL_ID, 'model_revision': MODEL_REVISION, 'model_version': main.MODEL_VERSION,
              'temperature': main.health()['temperature'], 'confidence_threshold': main.health()['confidence_threshold'],
              'main_py_sha256': sha256(Path(main.__file__).read_bytes()),
              'manifest_sha256': sha256(MANIFEST.read_bytes()), 'dataset_doi': DOI,
              'environment': {'python': platform.python_version(), **{name: version(name) for name in ['torch', 'transformers', 'pillow', 'numpy', 'huggingface-hub', 'safetensors']}},
              'metrics': metrics(rows), 'failure_count': 0}
    with (DOCS / 'maize-predictions.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    with (DOCS / 'maize-confusion-matrix.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream); writer.writerow(['actual/predicted', *NAMES])
        writer.writerows([[name, *row] for name, row in zip(NAMES, result['metrics']['confusion_matrix'])])
    json_file(DOCS / 'maize-metrics.json', result)
    json_file(DOCS / 'maize-overlap-audit.json', audit)
    write_report(result, manifest, audit)
    json_file(DOCS / 'maize-evaluation-status.json', {'status': 'completed', 'timestamp_lagos': result['timestamp_lagos'], 'processed': 40, 'failure_count': 0})
    print(json.dumps(result['metrics'], indent=2), flush=True)


if __name__ == '__main__':
    try:
        run()
    except Exception as exc:
        DOCS.mkdir(parents=True, exist_ok=True)
        json_file(DOCS / 'maize-evaluation-status.json', {'status': 'failed', 'error': f'{type(exc).__name__}: {exc}', 'completed_run': False})
        traceback.print_exc()
        sys.exit(1)
