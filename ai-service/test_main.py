import io
import unittest
import asyncio
import os
from unittest.mock import patch

from fastapi import HTTPException
from fastapi import UploadFile
from starlette.datastructures import Headers
from PIL import Image
import main


class ImageValidationTests(unittest.TestCase):
    def test_catalogue_has_disjoint_classes_and_marks_single_class_crops(self):
        classes = [label for spec in main.CROPS.values() for label in spec['classes']]
        self.assertEqual(len(main.CROPS), 14)
        self.assertEqual(len(classes), 38)
        self.assertEqual(len(set(classes)), 38)
        for spec in main.CROPS.values():
            self.assertTrue(all(label.startswith(spec['prefix']) for label in spec['classes']))
            if len(spec['classes']) == 1:
                self.assertNotEqual(spec['coverage'], 'healthy_and_diseases')

    def test_matching_publisher_calibration_is_required(self):
        calibration = {'temperature': .8845188130635788}
        threshold = {'status': 'selected', 'threshold': .5, 'temperature': .8845188130635788}
        self.assertEqual(main.calibration_settings(calibration, threshold), (.8845188130635788, .5))
        for invalid in [0, -1, float('nan'), float('inf')]:
            with self.subTest(temperature=invalid), self.assertRaises(ValueError):
                main.calibration_settings({'temperature': invalid}, threshold)
        with self.assertRaises(ValueError):
            main.calibration_settings(calibration, {**threshold, 'temperature': 2})
        with self.assertRaises(ValueError):
            main.calibration_settings(calibration, {**threshold, 'threshold': 1.5})

    def image(self, fmt='PNG'):
        stream = io.BytesIO()
        Image.new('RGB', (24, 24), 'green').save(stream, format=fmt)
        return stream.getvalue()

    def test_corrupt_image_rejected(self):
        with self.assertRaises(HTTPException) as error:
            main.classify(b'not an image', 'tomato')
        self.assertEqual(error.exception.status_code, 422)

    def test_disguised_gif_rejected(self):
        with self.assertRaises(HTTPException) as error:
            main.classify(self.image('GIF'), 'tomato')
        self.assertEqual(error.exception.status_code, 422)

    def test_unavailable_model_explains_loading(self):
        with patch.object(main, '_model', None), patch.object(main, '_status', 'loading'):
            with self.assertRaises(HTTPException) as error:
                main.classify(self.image(), 'tomato')
            self.assertEqual(error.exception.status_code, 503)
            self.assertIn('initializing', error.exception.detail)

    def test_pixel_limit(self):
        with patch.object(main, 'MAX_PIXELS', 100):
            with self.assertRaises(HTTPException) as error:
                main.classify(self.image(), 'tomato')
            self.assertEqual(error.exception.status_code, 422)

    def test_human_labels(self):
        result = main.readable_prediction('Tomato___Early_blight', .75)
        self.assertEqual(result['crop'], 'Tomato')
        self.assertEqual(result['disease'], 'Early blight')
        self.assertEqual(result['confidence'], .75)

    def test_unsupported_crops_rejected_before_inference(self):
        for crop in ['cassava', 'rice', '', None]:
            with self.subTest(crop=crop), self.assertRaises(HTTPException) as error:
                main.classify(self.image(), crop)
            self.assertEqual(error.exception.status_code, 422)

    def test_upload_over_five_mb(self):
        upload = UploadFile(io.BytesIO(b'x' * (main.MAX_BYTES + 1)),
                            headers=Headers({'content-type': 'image/png'}))
        with self.assertRaises(HTTPException) as error:
            asyncio.run(main.predict(upload, 'tomato'))
        self.assertEqual(error.exception.status_code, 413)
        self.assertTrue(upload.file.closed)

    def test_unsupported_mime(self):
        upload = UploadFile(io.BytesIO(b'text'), headers=Headers({'content-type': 'text/plain'}))
        with self.assertRaises(HTTPException) as error:
            asyncio.run(main.predict(upload, 'tomato'))
        self.assertEqual(error.exception.status_code, 422)


@unittest.skipUnless(os.environ.get('RUN_MODEL_TESTS') == '1', 'Opt-in real model test; requires cached model or network')
class ModelIntegrationTests(unittest.TestCase):
    def test_real_leaf_classification(self):
        main.get_classifier()
        content = (main.BASE_DIR / '.model-cache/test-tomato-early-blight.jpg').read_bytes()
        result = main.classify(content, 'tomato')
        self.assertEqual(len(result['top_predictions']), 3)
        self.assertEqual(result['label'], 'Tomato___Early_blight')
        self.assertGreater(result['confidence'], 0)
        self.assertEqual(result['model_version'], 'v1.1')
        self.assertAlmostEqual(main.health()['temperature'], .8845188130635788)
        self.assertEqual(result['uncertain'], result['confidence'] < result['confidence_threshold'])
        self.assertTrue(main.health()['model_loaded'])

    def test_all_selected_crops_restrict_classes_without_inflating_scores(self):
        main.get_classifier()
        content = (main.BASE_DIR / '.model-cache/test-tomato-early-blight.jpg').read_bytes()
        for crop, count in [('tomato', 3), ('maize', 3), ('pepper', 2)]:
            with self.subTest(crop=crop):
                result = main.classify(content, crop)
                self.assertEqual(result['selected_crop'], crop)
                self.assertEqual(len(result['top_predictions']), count)
                self.assertTrue(all(item['label'].startswith(main.CROP_PREFIXES[crop]) for item in result['top_predictions']))
                scores = [item['confidence'] for item in result['top_predictions']]
                self.assertEqual(scores, sorted(scores, reverse=True))
                if crop != 'tomato':
                    self.assertLess(result['confidence'], .5)
                    self.assertTrue(result['uncertain'])
                    self.assertEqual(result['uncertainty_reason'], 'crop_conflict')
                self.assertGreaterEqual(result['selected_crop_confidence'], result['confidence'])


if __name__ == '__main__':
    unittest.main()
