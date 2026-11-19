"""Build a source-audited mixed field/replay collection without touching production."""
import csv
import hashlib
import io
import json
import random
import re
import threading
import urllib.parse
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import main
from evaluate_maize import RangeArchive, FLAGS, CLASSES, fetch
from PIL import Image, ImageOps, UnidentifiedImageError

OUT = main.BASE_DIR / '.model-cache/field-training'
PD_COMMIT = '5467f6012d78d1c446145d5f582da6096f852ae8'
PD_REPO = 'pratikkayal/PlantDoc-Dataset'
SEED = 20261118
PD_LABELS = {
    'Bell_pepper leaf spot': 'Pepper,_bell___Bacterial_spot',
    'Tomato leaf': 'Tomato___healthy',
    'Tomato Early blight leaf': 'Tomato___Early_blight',
    'Tomato Septoria leaf spot': 'Tomato___Septoria_leaf_spot',
    'Tomato leaf bacterial spot': 'Tomato___Bacterial_spot',
    'Tomato leaf late blight': 'Tomato___Late_blight',
    'Tomato leaf mosaic virus': 'Tomato___Tomato_mosaic_virus',
    'Tomato leaf yellow virus': 'Tomato___Tomato_Yellow_Leaf_Curl_Virus',
    'Tomato mold leaf': 'Tomato___Leaf_Mold',
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def signature(data):
    if len(data) > main.MAX_BYTES:
        raise ValueError('over_5_MiB')
    with Image.open(io.BytesIO(data)) as image:
        if image.format not in {'JPEG', 'PNG', 'WEBP'} or getattr(image, 'is_animated', False):
            raise ValueError('unsupported_image')
        if image.width * image.height > main.MAX_PIXELS:
            raise ValueError('over_20_megapixels')
        image = ImageOps.exif_transpose(image).convert('RGB')
        exact = digest(str(image.size).encode() + image.tobytes())
        pixels = image.convert('L').resize((9, 8), Image.Resampling.LANCZOS).tobytes()
        dhash = sum((pixels[y * 9 + x] > pixels[y * 9 + x + 1]) << (y * 8 + x)
                    for y in range(8) for x in range(8))
    return exact, dhash


def inferred_group(filename):
    stem = Path(filename).stem.casefold()
    # These are heuristics, not verified plant IDs. Record that limitation explicitly.
    leaf = re.search(r'cimg\d+_(\d+-\d+)-\d+$', stem)
    if leaf:
        return 'pretoria:inferred-leaf:' + leaf.group(1)
    timestamp = re.search(r'(20\d{6})[_-](\d{4})\d{2}', stem)
    if timestamp:
        return 'pretoria:inferred-minute:' + ''.join(timestamp.groups())
    stem = re.sub(r'[_ -]?burst\d+|[_ -]?copy.*', '', stem)
    return 'pretoria:unknown:' + stem


def audit_sources(rows, tree_bytes):
    """Audit cached, pinned source manifests without repeating rate-limited API requests."""
    from huggingface_hub import hf_hub_download
    tree = json.loads(tree_bytes)
    if tree.get('sha') != PD_COMMIT or tree.get('truncated'):
        raise ValueError('Cached PlantDoc tree does not match the pinned source')
    pd_names = {Path(item['path']).name.casefold() for item in tree['tree'] if item['type'] == 'blob'}
    pv_names, evidence = {}, {}
    for revision in ['3a2cce39a518f6ae887fbbe01b6db35ad1209bf0', main.MODEL_REVISION]:
        path = Path(hf_hub_download(main.MODEL_ID, 'splits.json', revision=revision, local_files_only=True))
        raw = path.read_bytes()
        splits = json.loads(raw)['splits']
        pv_names[revision] = {split: {Path(item[0]).name.casefold() for item in items} for split, items in splits.items()}
        evidence[revision] = {'splits_sha256': digest(raw), 'sizes': {split: len(items) for split, items in splits.items()}}
    checks = []
    for row in rows:
        if row['origin'] != 'pretoria_field':
            continue
        filename = Path(row['source'].split('#', 1)[1]).name
        name = filename.casefold()
        checks.append(dict(filename=filename, split=row['split'], label=row['label'],
                           plantdoc_filename_match=name in pd_names,
                           plantvillage_matches=[f'{revision}/{split}' for revision, splits in pv_names.items()
                                                 for split, members in splits.items() if name in members]))
    return dict(method='Case-insensitive basename checks against pinned cached publisher/source manifests',
                plantdoc_commit=PD_COMMIT, plantdoc_tree_sha256=digest(tree_bytes), plantvillage=evidence,
                checked_university_images=len(checks),
                matches=[item for item in checks if item['plantdoc_filename_match'] or item['plantvillage_matches']],
                checks=checks,
                limitation='This is not a pixel/perceptual audit of every publisher training image. Renamed/recompressed copies and undisclosed sources cannot be excluded. PlantDoc and replay overlap is declared regardless of these filename checks.')


class Selection:
    def __init__(self):
        self.rows, self.exclusions = [], []
        self.exact, self.near, self.groups = set(), [], {}
        self.review = json.loads((main.BASE_DIR / 'training/field-review-exclusions.json').read_text(encoding='utf-8'))

    def consider(self, path, label, split, group, source, origin):
        if source in self.review['excluded_sources']:
            self.exclusions.append({'source': source, 'reason': 'manual_content_review: ' + self.review['excluded_sources'][source]})
            return False
        data = path.read_bytes()
        try:
            exact, near = signature(data)
        except (ValueError, OSError, UnidentifiedImageError) as exc:
            self.exclusions.append({'source': source, 'reason': str(exc)})
            return False
        reason = 'exact_duplicate_or_protected' if exact in self.exact else 'near_duplicate_or_protected' if any((near ^ previous).bit_count() <= 4 for previous in self.near) else 'group_crosses_split' if group in self.groups and self.groups[group] != split else None
        if reason:
            self.exclusions.append({'source': source, 'reason': reason})
            return False
        self.exact.add(exact)
        self.near.append(near)
        self.groups[group] = split
        self.rows.append(dict(path=str(path.resolve().relative_to(main.BASE_DIR.resolve())).replace('\\', '/'),
                              label=label, split=split, group=group, source=source, sha256=digest(data),
                              origin=origin, decoded_rgb_sha256=exact, dhash=f'{near:016x}'))
        return True


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'preparation-status.json').write_text(json.dumps({'status': 'running'}))
    # Remove no files; a failed preparation leaves cached images available for retry.
    protected = json.loads((main.BASE_DIR / 'evaluation/maize-manifest.json').read_text())
    select = Selection()
    protected_groups = {inferred_group(row['filename']) for row in protected['samples']}
    for sample in protected['samples']:
        data = (main.BASE_DIR / '.model-cache/maize-evaluation' / sample['cache_name']).read_bytes()
        if digest(data) != sample['sha256']:
            raise ValueError('Protected benchmark checksum mismatch')
        exact, near = signature(data)
        select.exact.add(exact)
        select.near.append(near)
    # Preserve the old replay splits and do not move any old test image into training.
    replay = main.BASE_DIR / '.model-cache/training-pilot'
    with (replay / 'manifest.csv').open(newline='', encoding='utf-8') as stream:
        for row in csv.DictReader(stream):
            path = replay / row['path']
            if digest(path.read_bytes()) != row['sha256']:
                raise ValueError('Replay image checksum mismatch')
            exact, near = signature(path.read_bytes())
            if exact in select.exact:
                raise ValueError('Replay collection overlaps protected benchmark or itself')
            select.exact.add(exact)
            select.near.append(near)
            select.groups[row['group']] = row['split']
            select.rows.append({**row, 'path': str(path.relative_to(main.BASE_DIR)).replace('\\', '/'),
                                'origin': 'plantvillage_replay', 'decoded_rgb_sha256': exact, 'dhash': f'{near:016x}'})

    article = json.loads((main.BASE_DIR / '.model-cache/maize-evaluation/article.json').read_text())
    files = {entry['name']: entry for entry in article['files']}
    raw_labels = (main.BASE_DIR / '.model-cache/maize-evaluation/Database.csv').read_bytes()
    if digest(raw_labels) != protected['label_csv_sha256']:
        raise ValueError('University annotation checksum mismatch')
    annotations = list(csv.DictReader(io.StringIO(raw_labels.decode('utf-8-sig'))))
    archive_info = files['leaf_images.zip']
    remote = RangeArchive(archive_info['download_url'], archive_info['size'])
    with zipfile.ZipFile(remote) as archive:
        originals = [info for info in archive.infolist() if not info.is_dir()]
        entries = {Path(info.filename).name: info for info in originals}
        if len(entries) != len(originals):
            raise ValueError('Ambiguous source archive basenames')
    local = threading.local()
    archives = []
    def download_pretoria(row):
        entry = entries[row['filePath']]
        path = OUT / 'pretoria' / (digest(entry.filename.encode())[:20] + '.jpg')
        path.parent.mkdir(parents=True, exist_ok=True)
        import zlib
        if not path.exists():
            if not hasattr(local, 'archive'):
                local.archive = zipfile.ZipFile(RangeArchive(archive_info['download_url'], archive_info['size']))
                archives.append(local.archive)
            data = local.archive.read(entry.filename)
            temporary = path.with_suffix('.part')
            temporary.write_bytes(data)
            temporary.replace(path)
        data = path.read_bytes()
        if len(data) != entry.file_size or zlib.crc32(data) != entry.CRC:
            raise ValueError('University image ZIP checksum mismatch')
        return row, path, entry.filename
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            for flag, (_, label) in CLASSES.items():
                candidates = [row for row in annotations if row[flag] == '1' and sum(int(row[key]) for key in FLAGS) == 1
                              and row['filePath'] in entries and entries[row['filePath']].file_size <= main.MAX_BYTES
                              and inferred_group(row['filePath']) not in protected_groups]
                random.Random(f'{SEED}:{flag}').shuffle(candidates := sorted(candidates, key=lambda row: row['filePath']))
                accepted = 0
                # Fetch in small batches; selection uses image properties only, never predictions.
                for offset in range(0, len(candidates), 4):
                    for row, path, member in pool.map(download_pretoria, candidates[offset:offset + 4]):
                        split = 'train' if accepted < 12 else 'validation' if accepted < 16 else 'test'
                        if select.consider(path, label, split, inferred_group(row['filePath']),
                                           protected['doi'] + '#' + member, 'pretoria_field'):
                            accepted += 1
                        if accepted == 20:
                            break
                    print(f'University field {flag}: {accepted}/20', flush=True)
                    if accepted == 20:
                        break
                if accepted != 20:
                    raise RuntimeError(f'Not enough eligible {flag} photographs after exclusions: {accepted}/20')
    finally:
        for archive in archives:
            archive.close()

    tree_path = OUT / 'plantdoc-tree.json'
    if not tree_path.exists():
        tree_path.write_bytes(fetch(f'https://api.github.com/repos/{PD_REPO}/git/trees/{PD_COMMIT}?recursive=1', 5_000_000)[0])
    tree = json.loads(tree_path.read_text())
    if tree.get('truncated'):
        raise ValueError('PlantDoc tree is truncated')
    def download_pd(item):
        url = f'https://raw.githubusercontent.com/{PD_REPO}/{PD_COMMIT}/' + urllib.parse.quote(item['path'])
        path = OUT / 'plantdoc' / (digest(item['path'].encode())[:24] + Path(item['path']).suffix.lower())
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            data = fetch(url, main.MAX_BYTES)[0]
            if hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() != item['sha']:
                raise ValueError('PlantDoc Git blob checksum mismatch')
            temporary = path.with_suffix('.part')
            temporary.write_bytes(data)
            temporary.replace(path)
        data = path.read_bytes()
        if hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() != item['sha']:
            raise ValueError('Cached PlantDoc Git blob checksum mismatch')
        return path, url
    with ThreadPoolExecutor(max_workers=4) as pool:
        for directory, label in PD_LABELS.items():
            for official_split, target_count in [('train', 10), ('test', 2)]:
                candidates = [item for item in tree['tree'] if item['type'] == 'blob' and len(item['path'].split('/')) == 3
                              and item['path'].split('/')[:2] == [official_split, directory]
                              and item.get('size', 0) <= main.MAX_BYTES]
                random.Random(f'{SEED}:{directory}:{official_split}').shuffle(candidates := sorted(candidates, key=lambda item: item['path']))
                accepted = 0
                for offset in range(0, len(candidates), 4):
                    batch = candidates[offset:offset + 4]
                    for item, (path, url) in zip(batch, pool.map(download_pd, batch)):
                        split = 'test' if official_split == 'test' else 'train' if accepted < 8 else 'validation'
                        # Web source plant IDs are unavailable. Filename plus duplicate filtering is a heuristic.
                        group = 'plantdoc:unknown:' + Path(item['path']).name.casefold()
                        if select.consider(path, label, split, group, url, 'plantdoc_field_web'):
                            accepted += 1
                        if accepted == target_count:
                            break
                    if accepted == target_count:
                        break
                if accepted != target_count:
                    raise RuntimeError(f'Not enough eligible PlantDoc images for {directory}/{official_split}: {accepted}')
            print(f'PlantDoc {directory}: 12 prepared', flush=True)
    # Paths in the generated CSV are relative to OUT, not to the project or current shell.
    import os
    for row in select.rows:
        row['path'] = os.path.relpath(main.BASE_DIR / row['path'], OUT).replace('\\', '/')
    audit = audit_sources(select.rows, tree_path.read_bytes())
    (OUT / 'overlap-audit.json').write_text(json.dumps(audit, indent=2))
    with (OUT / 'manifest.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(select.rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(select.rows)
    provenance = dict(seed=SEED, purpose='Field adaptation experiment; not independent all-crop accuracy certification',
                      sources=[dict(name=article['title'], doi=protected['doi'], author='Hamish Craze', license=article['license']),
                               dict(name='Cropped-PlantDoc', authors='Davinder Singh, Naman Jain, Pranjali Jain, Pratik Kayal, Sudhakar Kumawat, Nipun Batra',
                                    repository=f'https://github.com/{PD_REPO}', revision=PD_COMMIT, license='CC BY 4.0'),
                               dict(name='PlantVillage replay', original_manifest_sha256=digest((replay / 'manifest.csv').read_bytes()))],
                      protected_benchmark='40 original maize photographs and their near matches/inferred groups excluded',
                      near_duplicate_filter='64-bit horizontal dHash, Hamming distance <=4; conservative heuristic, not proof of independence',
                      grouping='University inferred leaf IDs/minute timestamps where available; other IDs are filename fallbacks. No verified plant/session separation.',
                      label_mapping=PD_LABELS,
                      field_gaps=['Tomato Target Spot, Spider mites, and healthy bell pepper: PlantVillage replay only. Unverified/mixed-crop PlantDoc folders excluded.'],
                      manual_content_review=select.review,
                      pretrained_overlap='Publisher v1.1 already trained on PlantVillage and Cropped-PlantDoc. University dataset is not declared but web reuse/undisclosed overlap cannot be excluded.',
                      alternative_review='PlantWild/v2 investigated; not selected for this run: BY-NC-ND terms, large archives and additional taxonomy/overlap review required.',
                      excluded=select.exclusions, total_images=len(select.rows))
    (OUT / 'provenance.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
    (OUT / 'preparation-status.json').write_text(json.dumps({
        'status': 'completed', 'manifest_sha256': digest((OUT / 'manifest.csv').read_bytes()),
        'images': len(select.rows)}, indent=2))
    print(f'Completed collection: {len(select.rows)} images. {OUT / "manifest.csv"}', flush=True)


if __name__ == '__main__':
    try:
        run()
    except Exception as exc:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / 'preparation-status.json').write_text(json.dumps({'status': 'failed', 'error': f'{type(exc).__name__}: {exc}'}))
        raise
