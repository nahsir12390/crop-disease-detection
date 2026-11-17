# First fine-tuning run: 17 November 2026

We successfully trained and saved a real candidate model for Tomato, Maize and Bell Pepper. The small training run improved the laboratory-photo pilot score by one image, but **did not improve the maize field-photo score**. The candidate was not deployed. The working Laravel application and production model remain unchanged.

## What actually ran

The existing Python 3.12 `.venv` and CPU PyTorch 2.6.0 were used; no global packages or paid GPU jobs were needed. Starting checkpoint: `neghani/plantvillage-mobilenetv2`, revision `77e6d262dca53b818f7ad1d67088700754515639`. The matching image processor and 38-class model output were preserved.

We downloaded 288 real labeled PlantVillage photographs covering 16 supported classes: 10 tomato classes, 4 maize classes and 2 bell pepper classes. Each class had 12 training, 3 validation and 3 test images: **192 training, 48 validation and 48 test** in total. Training used the classifier head only, AdamW, learning rate 0.0001, batch size 8, seed 20261117, and two epochs. Training loss decreased from 0.2210 to 0.1962. Both epochs had validation macro F1 of approximately 0.9786; the first tied-best epoch was retained.

The script selected one photograph per available source leaf group. For 145 of the 288 photographs, no unambiguous leaf-map group was available, so source identifiers were used. Exact decoded duplicate checks and split-group checks passed; unknown plant identities and near duplicates remain limitations.

## Real prediction results

| Test | Original model | Fine-tuned candidate | Interpretation |
| --- | --- | --- | --- |
| 48 PlantVillage pilot images, all three crops | 47/48 (97.92%) | 48/48 (100%) | Pipeline check with potential pretrained-data overlap |
| Previous 40 maize field images | 18/40 (45%) | 18/40 (45%) | No observed field improvement |

The candidate was saved to disk and loaded again for the field comparison. That comparison calls the actual application's `classify()` function with maize selected. Both models use the same image validation and crop-restricted ranking logic. No predictions are random, mocked, or supplied from the expected labels.

| Maize category | Original correct | Candidate correct |
| --- | --- | --- |
| Gray leaf spot | 0/10 | 0/10 |
| Common rust | 8/10 | 8/10 |
| Northern leaf blight | 6/10 | 6/10 |
| Healthy | 4/10 | 4/10 |

All per-class precision, recall, F1 scores and confusion matrices are in the machine-readable reports. The per-image CSVs allow the counts to be checked directly.

## What this means in simple English

The training system works, but this small exercise did not make the model better at recognizing the maize field photos. Getting every laboratory test image right does not mean it can diagnose every real leaf correctly. The base model already learned from PlantVillage, so these 48 pilot images are not an independent accuracy test. The 40 field photographs have already been observed during development; they are a regression benchmark, not a new blind test, and complete exclusion from the publisher's training data cannot be proved.

Common rust had the most correct field identifications, although it was also incorrectly predicted for other diseases. Gray leaf spot remains a serious weakness. Tomato and pepper field performance was not measured by this run. No improvement for those crops in real conditions can be claimed.

The next useful work is collecting or obtaining a larger, correctly labeled **field-photo** collection for all three crops. Keep whole plants/sessions together when splitting it. Focus especially on gray leaf spot and healthy maize, while including all supported classes to limit regressions. Verify disease labels with an agricultural expert, keep the existing benchmark out of training, and reserve a new independent test collection. Use that evidence to decide whether further head training or backbone fine-tuning improves the model. Simply increasing epochs on this tiny pilot is not evidence of improvement.

Candidate confidence scores are uncalibrated (temperature 1). Publisher calibration must not be reused for changed weights. Validation-set calibration, uncertainty testing and independent field evaluation are required before considering deployment. The production model remains the current v1.1 snapshot.

## Files and reproduction

- [Training instructions](model-training.md)
- [Pilot report](../ai-service/training/pilot-01/report.json)
- [Pilot predictions](../ai-service/training/pilot-01/predictions.csv)
- [Field comparison report](../ai-service/training/pilot-01/field-report.json)
- [Field predictions](../ai-service/training/pilot-01/field-predictions.csv)
- [Selection manifest](../ai-service/training/pilot-01/manifest.csv) and [provenance](../ai-service/training/pilot-01/provenance.json)

The archived manifest records the actual selected images and source URLs; its image paths are relative to the original `.model-cache/training-pilot` directory. Data and weights are deliberately excluded from Git. The local candidate is at `ai-service/.model-cache/training-runs/pilot-01/checkpoint/`.

After reproducing the pilot commands in the training guide, run the existing cached field benchmark with:

```powershell
.\ai-service\.venv\Scripts\python.exe ai-service/evaluate_candidate.py --checkpoint ai-service/.model-cache/training-runs/pilot-01/checkpoint --output ai-service/.model-cache/training-runs/pilot-01/field-regression
```

Use a new output directory if that run already exists. If the 40 benchmark photographs are not cached, first follow `docs/model-evaluation.md` to restore them. Missing or checksum-mismatched images stop the comparison; they are never replaced with invented results.

Verification: 18 Python tests ran, 16 passed and 2 opt-in model integration tests were skipped. Separately, the actual training and 48-image comparison completed, and the actual 40-image baseline/candidate field comparison completed. The saved candidate loaded with the expected label map and no missing/mismatched weights.
