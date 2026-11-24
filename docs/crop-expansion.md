# Crop expansion: 23 November 2026

The existing application now exposes all 14 crop types and 38 classes already present in its pinned MobileNetV2 v1.1 checkpoint. The earlier portal exposed only Tomato, Maize and bell Pepper. This change enables the existing trained classes; it does not claim new training or changed model weights.

## Available crops

| Crop | Classes | Coverage | Matched source labels in integration check |
| --- | ---: | --- | ---: |
| Tomato | 10 | healthy and diseases | 29/30 |
| Maize | 4 | healthy and diseases | 11/12 |
| Bell pepper | 2 | healthy and diseases | 6/6 |
| Potato | 3 | healthy and diseases | 9/9 |
| Apple | 4 | healthy and diseases | 12/12 |
| Grape | 4 | healthy and diseases | 12/12 |
| Cherry (including sour) | 2 | healthy and diseases | 6/6 |
| Peach | 2 | healthy and diseases | 6/6 |
| Strawberry | 2 | healthy and diseases | 6/6 |
| Orange | 1 | disease only | 3/3 |
| Squash | 1 | disease only | 3/3 |
| Soybean | 1 | healthy only | 3/3 |
| Blueberry | 1 | healthy only | 3/3 |
| Raspberry | 1 | healthy only | 3/3 |

Healthy-only classes (Blueberry, Raspberry and Soybean) cannot identify diseases or certify that a leaf is healthy. Orange has only a citrus-greening class; Squash has only a powdery-mildew class. Neither includes a healthy reference. These five crop types are labeled **limited coverage** in the selector and their results remain unconfirmed regardless of score. Selecting a single-class crop always leaves one possible crop-restricted result, so its label-match count is not disease-detection accuracy.

Potato, Apple, Grape, Cherry, Peach and Strawberry provide additional healthy/disease class choices. Their coverage remains limited to the exact classes listed on the About page and beside the upload form. Cassava, rice, beans and other unlisted crops remain unsupported; they were not added with invented labels.

## Real verification

The actual pinned model processed 114 real labeled PlantVillage images: three per model class. 112 crop-restricted predictions matched the source labels; two did not. The single-class examples are included in that total and must not be interpreted as successful disease discrimination. Photos were downloaded from `spMohanty/PlantVillage-Dataset` at `7f7ecc7e1eaca78107e3affe7cb5abd9427e139a` with Git blob checksums verified. No generated images or mocked predictions were used for this check.

**This is integration verification, not independent accuracy testing.** PlantVillage was used for pretraining; these exact images may have been seen during training. These are laboratory-style photos, and source labels/plant identity were not independently reviewed. The small selection does not establish field accuracy or replace the previous maize field reports. No new accuracy percentage is advertised by the application.

Individual source URLs, expected labels, actual predictions, raw model confidences, uncertainty flags and checksums are saved in [predictions.csv](../ai-service/evaluation/crop-catalogue/predictions.csv). The [machine-readable report](../ai-service/evaluation/crop-catalogue/report.json) and [completion status](../ai-service/evaluation/crop-catalogue/status.json) record the run. Photos remain in ignored `.model-cache/crop-catalogue`; no dataset images or model weights are committed.

## Implementation

- A shared [crop catalogue](../ai-service/crops.json) supplies Laravel validation, FastAPI prefixes, exact class whitelists and UI options. Model initialization checks that its complete class map matches this catalogue.
- The upload form lists available classes and explains coverage. Limited-class results are forced to unconfirmed in both FastAPI and Laravel; their original softmax scores are not inflated.
- Existing registration, portal authentication, admin access, image validation and publisher calibration remain in place.
- The prior three-crop training pilot remains scoped to its original 16 classes so existing reproduction commands continue to work.
- The model remains `neghani/plantvillage-mobilenetv2` revision `77e6d262dca53b818f7ad1d67088700754515639`. The [publisher model card](https://huggingface.co/neghani/plantvillage-mobilenetv2) describes its training sources and limitations.

## Reproduce

From the project root, using the existing virtual environment:

```powershell
.\ai-service\.venv\Scripts\python.exe ai-service/evaluate_crop_catalogue.py
php artisan test
npm.cmd run build
```

The evaluator caches downloads and fails with a recorded status if metadata, downloads, class compatibility or inference fails. Do not treat a previous report as proof of a new successful run if status is failed. On local development, restart FastAPI after pulling the new catalogue. On Render, deploy the latest feature-branch commit; the Docker build verifies model initialization and picks up the shared JSON automatically. Existing environment settings and admin credentials remain valid.

## How to explain it to the supervisor

> The system uses a pretrained MobileNetV2 model covering 38 classes across 14 crop types. We expanded the portal to expose those existing trained classes and verified their integration with real labeled images. Some crops have limited reference classes, so the system displays uncertainty and coverage notices. The expansion does not represent new custom training or independently verified field accuracy.
