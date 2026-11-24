"""Fine-tune a candidate without changing production. Uses existing PyTorch/Transformers."""
import argparse
import csv
import hashlib
import json
import random
from collections import Counter
from pathlib import Path

import main
import torch
from PIL import Image, ImageOps
from torch.utils.data import DataLoader, Dataset


def load_rows(manifest, labels):
    preparation_status = manifest.parent / 'preparation-status.json'
    if preparation_status.exists():
        status = json.loads(preparation_status.read_text())
        if status.get('status') != 'completed' or status.get('manifest_sha256') != hashlib.sha256(manifest.read_bytes()).hexdigest():
            raise ValueError('Dataset preparation is incomplete/failed or its manifest changed; rerun preparation')
    with manifest.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError('Empty training manifest')
    groups, hashes = {}, {}
    protected_path = main.BASE_DIR / 'evaluation/maize-manifest.json'
    protected = {sample['sha256'] for sample in json.loads(protected_path.read_text())['samples']} if protected_path.exists() else set()
    for row in rows:
        if row['split'] not in {'train', 'validation', 'test'} or row['label'] not in labels:
            raise ValueError(f'Unsupported split or model label: {row}')
        if not row.get('group') or not row.get('source'):
            raise ValueError('Each image requires a plant/session group and source attribution')
        path = (manifest.parent / row['path']).resolve()
        raw_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if row['split'] != 'test' and raw_hash in protected:
            raise ValueError('A protected maize evaluation image was assigned to training/validation')
        if row.get('sha256') and raw_hash != row['sha256']:
            raise ValueError(f'Image checksum changed: {path}')
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert('RGB')
            digest = hashlib.sha256(str(image.size).encode() + image.tobytes()).hexdigest()
        if digest in hashes:
            raise ValueError(f'Duplicate decoded image: {path}')
        hashes[digest] = row['split']
        group = row['group']
        if group in groups and groups[group] != row['split']:
            raise ValueError(f'Plant/session group leaks across splits: {group}')
        groups[group] = row['split']
        row['resolved_path'] = str(path)
    by_split = {split: {r['label'] for r in rows if r['split'] == split} for split in ['train', 'validation', 'test']}
    if not by_split['train'] or any(value != by_split['train'] for value in by_split.values()):
        raise ValueError('All splits must contain the same nonempty set of classes')
    for prefix in main.CROP_PREFIXES.values():
        selected = {label for label in by_split['train'] if label.startswith(prefix)}
        if selected and selected != {label for label in labels if label.startswith(prefix)}:
            raise ValueError('Include every supported disease class for each selected crop')
    return rows


class Leaves(Dataset):
    def __init__(self, rows, processor, label2id, augment=False):
        self.rows, self.processor, self.label2id, self.augment = rows, processor, label2id, augment

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        with Image.open(row['resolved_path']) as source:
            image = ImageOps.exif_transpose(source).convert('RGB')
        if self.augment and random.random() < .5:
            image = ImageOps.mirror(image)
        pixels = self.processor(images=image, return_tensors='pt')['pixel_values'][0]
        return pixels, self.label2id[row['label']]


def metrics(rows, predictions, labels):
    if len(rows) != len(predictions) or not rows:
        raise ValueError('Every evaluation image must have exactly one real prediction')
    matrix = {actual: {predicted: 0 for predicted in labels} for actual in labels}
    for row, prediction in zip(rows, predictions):
        matrix[row['label']][prediction['predicted_label']] += 1
    per_class = {}
    for label in labels:
        tp = matrix[label][label]
        actual = sum(matrix[label].values())
        predicted = sum(matrix[other][label] for other in labels)
        precision, recall = tp / predicted if predicted else 0, tp / actual if actual else 0
        per_class[label] = dict(support=actual, precision=precision, recall=recall,
                               f1=2 * precision * recall / (precision + recall) if precision + recall else 0)
    correct = sum(matrix[label][label] for label in labels)
    observed = [value for value in per_class.values() if value['support']]
    return dict(total=len(rows), correct=correct, accuracy=correct / len(rows),
                macro_f1=sum(v['f1'] for v in observed) / len(observed),
                per_class=per_class, confusion_matrix=matrix)


def breakdown(rows, predictions, labels):
    """Keep lab, field and crop results visible instead of hiding gaps in a combined score."""
    result = {}
    for kind in ['origin', 'crop']:
        values = [row.get('origin', 'unspecified') if kind == 'origin' else
                  next(crop for crop, prefix in main.CROP_PREFIXES.items() if row['label'].startswith(prefix))
                  for row in rows]
        result[kind] = {}
        for value in sorted(set(values)):
            indices = [index for index, item in enumerate(values) if item == value]
            result[kind][value] = metrics([rows[index] for index in indices],
                                         [predictions[index] for index in indices], labels)
    return result


def evaluate(model, loader, rows, device, temperature=1):
    model.eval()
    predictions = []
    with torch.inference_mode():
        for pixels, _ in loader:
            scores = (model(pixel_values=pixels.to(device)).logits / temperature).softmax(-1).cpu()
            for scores_row, row in zip(scores, rows[len(predictions):]):
                prefix = next(prefix for prefix in main.CROP_PREFIXES.values() if row['label'].startswith(prefix))
                allowed = [i for i, label in model.config.id2label.items() if label.startswith(prefix)]
                index = max(allowed, key=lambda i: float(scores_row[i]))
                predictions.append(dict(predicted_label=model.config.id2label[index], confidence=float(scores_row[index])))
    return predictions


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--epochs', type=int, default=5)
    parser.add_argument('--batch-size', type=int, default=8)
    parser.add_argument('--lr', type=float, default=1e-4)
    parser.add_argument('--unfreeze', action='store_true', help='Train backbone too; slower and easier to overfit')
    parser.add_argument('--threads', type=int, default=2)
    args = parser.parse_args()
    if args.epochs < 1 or args.batch_size < 1 or args.lr <= 0 or args.threads < 1:
        parser.error('Epochs, batch size, learning rate and threads must be positive')
    if args.output.exists():
        parser.error('Output already exists; choose a new directory to preserve previous runs')
    torch.set_num_threads(args.threads)
    torch.manual_seed(20261117)
    random.seed(20261117)
    main.get_classifier()
    model, processor = main._model, main._processor
    rows = load_rows(args.manifest.resolve(), model.config.label2id)
    args.output.mkdir(parents=True)
    (args.output / 'status.json').write_text(json.dumps({'status': 'running'}))
    (args.output / 'manifest.csv').write_bytes(args.manifest.read_bytes())
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model.to(device)
    splits = {name: [r for r in rows if r['split'] == name] for name in ['train', 'validation', 'test']}
    labels = sorted({r['label'] for r in rows})
    loaders = {name: DataLoader(Leaves(items, processor, model.config.label2id, name == 'train'),
                              batch_size=args.batch_size, shuffle=name == 'train', num_workers=0)
               for name, items in splits.items()}
    baseline_predictions = evaluate(model, loaders['test'], splits['test'], device, main._temperature)
    baseline = metrics(splits['test'], baseline_predictions, labels)
    for name, parameter in model.named_parameters():
        parameter.requires_grad = args.unfreeze or name.startswith('classifier.')
    parameters = [p for p in model.parameters() if p.requires_grad]
    if not parameters:
        raise RuntimeError('No trainable classifier parameters found')
    optimizer = torch.optim.AdamW(parameters, lr=args.lr)
    best, best_score, history, best_epoch = None, -1, [], None
    for epoch in range(args.epochs):
        # Frozen backbone stays in eval mode to preserve batch-normalization statistics.
        model.train() if args.unfreeze else model.eval()
        model.classifier.train()
        loss_sum = 0
        for pixels, targets in loaders['train']:
            optimizer.zero_grad(set_to_none=True)
            loss = model(pixel_values=pixels.to(device), labels=targets.to(device)).loss
            if not torch.isfinite(loss):
                raise RuntimeError('Nonfinite training loss')
            loss.backward()
            optimizer.step()
            loss_sum += float(loss.detach()) * len(targets)
        predictions = evaluate(model, loaders['validation'], splits['validation'], device)
        score = metrics(splits['validation'], predictions, labels)
        history.append(dict(epoch=epoch + 1, train_loss=loss_sum / len(splits['train']), validation=score))
        print(f'Epoch {epoch + 1}: loss={history[-1]["train_loss"]:.4f}, validation macro F1={score["macro_f1"]:.4f}', flush=True)
        if score['macro_f1'] > best_score:
            best_score = score['macro_f1']
            best_epoch = epoch + 1
            best = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
    model.load_state_dict(best)
    predictions = evaluate(model, loaders['test'], splits['test'], device)
    candidate = metrics(splits['test'], predictions, labels)
    model.cpu().save_pretrained(args.output / 'checkpoint', safe_serialization=True)
    processor.save_pretrained(args.output / 'checkpoint')
    report = dict(base_model=main.MODEL_ID, revision=main.MODEL_REVISION, seed=20261117,
                  torch_version=torch.__version__,
                  device=str(device), epochs=args.epochs, learning_rate=args.lr, backbone_trainable=args.unfreeze,
                  selected_epoch=best_epoch,
                  counts={name: dict(Counter(r['label'] for r in items)) for name, items in splits.items()},
                  manifest_sha256=hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
                  baseline=baseline, candidate=candidate, history=history,
                  baseline_breakdown=breakdown(splits['test'], baseline_predictions, labels),
                  candidate_breakdown=breakdown(splits['test'], predictions, labels),
                  calibration='Candidate temperature=1 (uncalibrated). Publisher calibration must not be reused.',
                  deployment='Not deployed; requires independent field testing and validation-set calibration.')
    provenance = args.manifest.parent / 'provenance.json'
    if provenance.exists():
        report['data_provenance'] = json.loads(provenance.read_text())
    (args.output / 'report.json').write_text(json.dumps(report, indent=2))
    with (args.output / 'predictions.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=['path', 'source', 'origin', 'expected_label', 'baseline_label', 'candidate_label', 'candidate_confidence'])
        writer.writeheader()
        for row, old, new in zip(splits['test'], baseline_predictions, predictions):
            writer.writerow(dict(path=row['path'], source=row['source'], origin=row.get('origin', 'unspecified'), expected_label=row['label'],
                                 baseline_label=old['predicted_label'], candidate_label=new['predicted_label'], candidate_confidence=new['confidence']))
    (args.output / 'status.json').write_text(json.dumps({'status': 'completed'}))
    print(f'Completed: baseline {baseline["correct"]}/{baseline["total"]}; candidate {candidate["correct"]}/{candidate["total"]}. Not deployed.', flush=True)


if __name__ == '__main__':
    run()
