"""Download a reproducible PlantVillage PILOT; never an independent accuracy test."""
import argparse
import csv
import hashlib
import json
import random
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import main
from PIL import Image

REVISION = '7f7ecc7e1eaca78107e3affe7cb5abd9427e139a'
REPO = 'spMohanty/PlantVillage-Dataset'


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'CropDiseaseTraining/1.0'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                return response.read()
        except OSError:
            if attempt == 2:
                raise


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--train-per-class', type=int, default=20)
    parser.add_argument('--holdout-per-class', type=int, default=4)
    parser.add_argument('--output', type=Path, default=main.BASE_DIR / '.model-cache/training-pilot')
    args = parser.parse_args()
    if min(args.train_per_class, args.holdout_per_class) < 1:
        parser.error('All class counts must be positive')
    args.output.mkdir(parents=True, exist_ok=True)
    def tree_at(sha):
        tree_path = args.output / f'tree-{sha}.json'
        if not tree_path.exists():
            tree_path.write_bytes(fetch(f'https://api.github.com/repos/{REPO}/git/trees/{sha}'))
        tree = json.loads(tree_path.read_text())
        if tree.get('truncated'):
            raise RuntimeError('Source tree is truncated; refusing incomplete selection')
        return tree['tree']
    tree = tree_at(REVISION)
    for directory in ['raw', 'color']:
        tree = tree_at(next(item['sha'] for item in tree if item['path'] == directory))
    pools = {}
    for item in tree:
        label = item['path']
        if any(label.startswith(prefix) for prefix in main.CROP_PREFIXES.values()):
            pools[label] = [f'raw/color/{label}/{entry["path"]}' for entry in tree_at(item['sha'])
                            if entry['type'] == 'blob' and entry['path'].lower().endswith(('.jpg', '.jpeg', '.png'))]
    if len(pools) != 16:
        raise RuntimeError(f'Expected 16 supported classes, found {len(pools)}')
    grouping_path = args.output / 'source-leaf-groups.json'
    if not grouping_path.exists():
        grouping_path.write_bytes(fetch(f'https://raw.githubusercontent.com/{REPO}/{REVISION}/leaf_grouping/leaf-map.json'))
    grouping = json.loads(grouping_path.read_text())
    def group_for(source, label):
        identifier = Path(source).name.replace('_final_masked', '').split('___')[-1].split('copy')[0]
        for extension in ['.jpg', '.JPG', '.png', '.PNG']:
            identifier = identifier.replace(extension, '')
        matches = [entry for entry in grouping.get(identifier.lower().strip(), []) if entry.startswith(label + ':::')]
        return matches[0] if len(matches) == 1 else f'unknown:{label}:{identifier.lower().strip()}'
    rng = random.Random(20261117)
    rows, hashes, selected_groups = [], set(), set()
    for label, paths in sorted(pools.items()):
        rng.shuffle(paths := sorted(paths))
        count = args.train_per_class + 2 * args.holdout_per_class
        selected = []
        for source in paths:
            group = group_for(source, label)
            if group not in selected_groups:
                selected.append(source)
                selected_groups.add(group)
            if len(selected) == count:
                break
        if len(selected) < count:
            raise ValueError(f'Not enough source images for {label}')
        def download(source):
            target = args.output / 'images' / label / Path(source).name
            target.parent.mkdir(parents=True, exist_ok=True)
            url = f'https://raw.githubusercontent.com/{REPO}/{REVISION}/' + urllib.parse.quote(source)
            if not target.exists():
                data = fetch(url)
                # Atomic replacement prevents interrupted downloads being reused as complete files.
                temporary = target.with_suffix(target.suffix + '.part')
                temporary.write_bytes(data)
                temporary.replace(target)
            return source, target, url
        with ThreadPoolExecutor(max_workers=6) as pool:
            downloaded = list(pool.map(download, selected))
        for index, (source, target, url) in enumerate(downloaded):
            with Image.open(target) as image:
                image = image.convert('RGB')
                digest = hashlib.sha256(str(image.size).encode() + image.tobytes()).hexdigest()
            if digest in hashes:
                raise RuntimeError('Duplicate image detected; review selection before training')
            hashes.add(digest)
            split = 'train' if index < args.train_per_class else 'validation' if index < args.train_per_class + args.holdout_per_class else 'test'
            rows.append(dict(path=str(target.relative_to(args.output)), label=label, split=split,
                             group=group_for(source, label), source=url, sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
        print(f'{label}: {count} real images prepared', flush=True)
    with (args.output / 'manifest.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (args.output / 'provenance.json').write_text(json.dumps({
        'dataset': REPO, 'revision': REVISION, 'seed': 20261117,
        'purpose': 'Training pipeline pilot only; pretrained model used PlantVillage. Not independent evaluation.',
        'group_limit': 'Source leaf-map groups where available; unknown groups use source identifier. Unknown plant/session identities and near duplicates remain limitations.',
        'unknown_group_images': sum(row['group'].startswith('unknown:') for row in rows),
        'source': f'https://github.com/{REPO}', 'images': len(rows)}, indent=2))
    print(args.output / 'manifest.csv', flush=True)


if __name__ == '__main__':
    run()
