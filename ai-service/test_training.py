"""Synthetic fixtures test safeguards only; never used as training/evaluation evidence."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from train_model import breakdown, load_rows, metrics
from prepare_field_training import audit_sources, inferred_group, signature
from io import BytesIO


class TrainingSafetyTests(unittest.TestCase):
    def fixture(self, root, same_group=False, duplicate=False):
        rows = []
        for index, split in enumerate(['train', 'validation', 'test']):
            path = root / f'{index}.png'
            Image.new('RGB', (8, 8), (0 if duplicate else index * 60, 10, 20)).save(path)
            rows.append(dict(path=path.name, label='Tomato___healthy', split=split,
                             group='same' if same_group else str(index), source='unit-test-only'))
        manifest = root / 'manifest.csv'
        with manifest.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        return manifest

    def test_split_group_leakage_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'leaks'):
                load_rows(self.fixture(Path(directory), same_group=True), {'Tomato___healthy': 0})

    def test_duplicate_pixels_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                load_rows(self.fixture(Path(directory), duplicate=True), {'Tomato___healthy': 0})

    def test_valid_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(len(load_rows(self.fixture(Path(directory)), {'Tomato___healthy': 0})), 3)

    def test_failed_preparation_blocks_stale_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self.fixture(root)
            (root / 'preparation-status.json').write_text(json.dumps({'status': 'failed'}))
            with self.assertRaisesRegex(ValueError, 'preparation is incomplete'):
                load_rows(manifest, {'Tomato___healthy': 0})

    def test_metrics_count_errors_and_missing_predictions(self):
        rows = [{'label': 'a'}, {'label': 'a'}, {'label': 'b'}, {'label': 'b'}]
        predictions = [{'predicted_label': label} for label in ['a', 'a', 'a', 'b']]
        result = metrics(rows, predictions, ['a', 'b'])
        self.assertEqual(result['correct'], 3)
        self.assertEqual(result['accuracy'], .75)
        self.assertEqual(result['per_class']['b']['recall'], .5)
        self.assertAlmostEqual(result['per_class']['a']['precision'], 2 / 3)

    def test_missing_prediction_cannot_produce_accuracy(self):
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            metrics([{'label': 'a'}], [], ['a'])

    def test_related_university_leaf_and_burst_groups(self):
        self.assertEqual(inferred_group('105_CIMG3840_1-140-1.JPG'),
                         inferred_group('105_CIMG3841_1-140-2.JPG'))
        self.assertEqual(inferred_group('IMG_20190316_081413_BURST002.jpg'),
                         inferred_group('IMG_20190316_081450.jpg'))

    def test_domain_scores_are_separate(self):
        rows = [{'label': 'Tomato___healthy', 'origin': 'lab'},
                {'label': 'Tomato___healthy', 'origin': 'field'}]
        predictions = [{'predicted_label': 'Tomato___healthy'}, {'predicted_label': 'Tomato___Early_blight'}]
        result = breakdown(rows, predictions, ['Tomato___healthy', 'Tomato___Early_blight'])
        self.assertEqual(result['origin']['lab']['accuracy'], 1)
        self.assertEqual(result['origin']['field']['accuracy'], 0)

    def test_image_signature_identifies_reencoded_pixels(self):
        image = Image.new('RGB', (16, 16), (20, 100, 5))
        first, second = BytesIO(), BytesIO()
        image.save(first, 'PNG', compress_level=0)
        image.save(second, 'PNG', compress_level=9)
        self.assertNotEqual(first.getvalue(), second.getvalue())
        self.assertEqual(signature(first.getvalue()), signature(second.getvalue()))

    def test_wrong_cached_source_revision_rejected(self):
        with self.assertRaisesRegex(ValueError, 'pinned source'):
            audit_sources([], b'{"sha": "wrong", "tree": []}')


if __name__ == '__main__':
    unittest.main()
