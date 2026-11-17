"""Compare a LOCAL candidate to production on the protected 40-image maize benchmark.

Runs the actual application classify() in this process only; never edits production.
The benchmark has already been observed, so this is a regression check, not a new blind test.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import main
from train_model import metrics
from transformers import AutoImageProcessor, AutoModelForImageClassification


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Choose a new output directory')
    import torch
    torch.set_num_threads(2)
    manifest = json.loads((main.BASE_DIR / 'evaluation/maize-manifest.json').read_text())
    samples = manifest['samples']
    rows = [{'label': sample['expected_label']} for sample in samples]
    labels = sorted({row['label'] for row in rows})
    images = []
    for sample in samples:
        path = main.BASE_DIR / '.model-cache/maize-evaluation' / sample['cache_name']
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != sample['sha256']:
            raise ValueError(f'Benchmark image checksum mismatch: {path}')
        images.append(data)
    main.get_classifier()
    production_labels = main._model.config.id2label
    baseline = [main.classify(data, 'maize') for data in images]
    model, info = AutoModelForImageClassification.from_pretrained(
        args.checkpoint, local_files_only=True, use_safetensors=True, output_loading_info=True)
    if any(info.get(key) for key in ['missing_keys', 'unexpected_keys', 'mismatched_keys']):
        raise ValueError(f'Candidate has incompatible weights: {info}')
    if model.config.id2label != production_labels:
        raise ValueError('Candidate class mapping differs from production')
    main._model = model.eval()
    main._processor = AutoImageProcessor.from_pretrained(args.checkpoint, use_fast=False, local_files_only=True)
    main._temperature = 1.0
    candidate = [main.classify(data, 'maize') for data in images]
    def score(predictions):
        return metrics(rows, [{'predicted_label': p['label']} for p in predictions], labels)
    result = dict(baseline=score(baseline), candidate=score(candidate),
                  checkpoint=str(args.checkpoint), base_revision=main.MODEL_REVISION,
                  dataset=manifest['dataset'], doi=manifest['doi'],
                  limitation='Previously observed 40-image regression benchmark, not a new blind or independent test. Publisher training overlap cannot be completely ruled out.',
                  confidence='Candidate scores are uncalibrated. This comparison measures top-1 class accuracy, not diagnostic certainty.',
                  deployed=False)
    args.output.mkdir(parents=True)
    (args.output / 'report.json').write_text(json.dumps(result, indent=2))
    with (args.output / 'predictions.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=['sample_id', 'source_filename', 'expected_label', 'baseline_label', 'candidate_label', 'candidate_confidence'])
        writer.writeheader()
        for sample, old, new in zip(samples, baseline, candidate):
            writer.writerow(dict(sample_id=sample['sample_id'], source_filename=sample['filename'],
                                 expected_label=sample['expected_label'], baseline_label=old['label'],
                                 candidate_label=new['label'], candidate_confidence=new['confidence']))
    print(f'Field regression: baseline {result["baseline"]["correct"]}/40; candidate {result["candidate"]["correct"]}/40. Not deployed.', flush=True)


if __name__ == '__main__':
    run()
