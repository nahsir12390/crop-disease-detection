"""Synthetic fixtures test safeguards only; never used as training/evaluation evidence."""
import csv
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from train_model import load_rows, metrics


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


if __name__ == '__main__':
    unittest.main()
