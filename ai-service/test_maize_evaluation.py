"""Unit checks of evaluation arithmetic; these are NOT the real image evaluation."""
import unittest

from evaluate_maize import LABELS, metrics


class EvaluationMetricsTests(unittest.TestCase):
    def test_hand_counted_confusion_and_abstentions(self):
        # 8 decisions: 2 per class; matrix [[1,1,0,0],[0,2,0,0],[0,0,0,2],[0,0,1,1]].
        predicted = [0, 1, 1, 1, 3, 3, 2, 3]
        actual = [0, 0, 1, 1, 2, 2, 3, 3]
        rows = [{'expected_label': LABELS[a], 'predicted_label': LABELS[p],
                 'correct': a == p, 'uncertain': i >= 4, 'top3_correct': True}
                for i, (a, p) in enumerate(zip(actual, predicted))]
        result = metrics(rows)
        self.assertEqual(result['confusion_matrix'], [[1, 1, 0, 0], [0, 2, 0, 0], [0, 0, 0, 2], [0, 0, 1, 1]])
        self.assertEqual(result['correct'], 4)
        self.assertEqual(result['incorrect'], 4)
        self.assertEqual(result['accuracy'], .5)
        self.assertEqual(result['confident'], 4)
        self.assertEqual(result['correct_confident'], 3)
        self.assertEqual(result['confident_accuracy'], .75)
        self.assertEqual(result['coverage'], .5)
        self.assertAlmostEqual(result['per_class'][1]['precision'], 2/3)
        self.assertEqual(result['per_class'][1]['recall'], 1)
        self.assertAlmostEqual(result['per_class'][1]['f1'], .8)
        self.assertEqual(result['per_class'][2]['precision'], 0)
        self.assertAlmostEqual(result['macro']['precision'], (1 + 2/3 + 0 + 1/3)/4)
        self.assertLess(result['wilson_95_interval'][0], .5)
        self.assertGreater(result['wilson_95_interval'][1], .5)

    def test_no_confident_predictions_and_no_predicted_class(self):
        rows = [{'expected_label': label, 'predicted_label': LABELS[0], 'correct': label == LABELS[0],
                 'uncertain': True, 'top3_correct': False} for label in LABELS]
        result = metrics(rows)
        self.assertIsNone(result['confident_accuracy'])
        self.assertEqual(result['coverage'], 0)
        self.assertEqual(result['per_class'][1]['precision'], 0)
        self.assertEqual(result['top3_correct'], 0)


if __name__ == '__main__':
    unittest.main()
