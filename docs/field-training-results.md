# Field-training results: 17 November 2026

The real field-data fine-tuning experiment is complete. **The candidate was not deployed because overall held-out performance regressed.** The working Laravel application and pinned production model remain unchanged.

## Images and source review

We prepared 476 labeled images: 312 training, 82 validation and 82 held-out files. The collection contains 288 PlantVillage replay photographs, 80 additional university maize field photographs and 108 PlantDoc field/web photographs. Of the 312 images used for weight updates, 192 are replay, 48 university field and 72 PlantDoc. All labels are source annotations; no new expert disease-label verification was performed.

The protected 40-image maize benchmark was kept outside training and validation, with exact/near-image and inferred-group exclusions. Visual content screening removed apparent black-pepper/bell-pepper crop mismatches, infographics, collages and a fruit-focused example. The full healthy-pepper PlantDoc folder was excluded. Target spot, spider mites and healthy bell pepper therefore have replay examples only. Known source groups and duplicate checks reduce leakage but do not establish plant-, farm- or session-level independence.

See [source review and reproduction](field-training.md) for source licenses, authors, mappings, download restrictions and limitations. The [overlap audit](../ai-service/training/field-02/overlap-audit.json) checked all 80 additional maize basenames against pinned publisher/source manifests and found zero direct filename matches. This is not a complete pixel/perceptual audit of the original training data.

The promising [Bangladesh tomato field dataset](https://data.mendeley.com/datasets/jttrv2w27r/1) could not be downloaded from this laptop: page/API requests returned HTTP 403. It was not used. Further GitHub API requests became rate-limited; the completed overlap audit used the already cached, pinned source tree with its commit and checksum validated.

## Actual training

The existing Python 3.12 virtual environment and CPU PyTorch 2.6.0+cpu were used. Starting model: `neghani/plantvillage-mobilenetv2` at `77e6d262dca53b818f7ad1d67088700754515639`. Training ran four epochs with all layers trainable, AdamW learning rate 0.00001, batch size 8 and seed 20261117. The original processor, class order and 38-class output were preserved. No global packages or paid cloud jobs were installed/started.

| Epoch | Training loss | Validation macro F1 |
| --- | ---: | ---: |
| 1 | 1.5663 | 0.7715 |
| 2 | 1.3519 | 0.8160 |
| 3 | 1.2868 | 0.7643 |
| 4 | 1.1237 | 0.7077 |

Epoch **2** was selected using validation macro F1. Test outcomes were not used to choose the saved epoch. Decreasing training loss did not guarantee better validation performance; later epochs performed worse on validation. This suggests overfitting, but this experiment does not establish the exact cause of every error.

An earlier `field-01` attempt was stopped for an additional collage exclusion during replacement-image review. It is marked aborted and has no reported experiment result. `field-02` is the completed experiment; exclusions were based on image content, not prediction correctness.

## Real prediction results

| Evaluation | Original model | Candidate |
| --- | ---: | ---: |
| Combined 82 held-out files | 65/82 (79.27%) | 58/82 (70.73%) |
| PlantVillage replay subset | 47/48 (97.92%) | 41/48 (85.42%) |
| PlantDoc field/web subset | 9/18 (50.00%) | 8/18 (44.44%) |
| New university maize subset | 9/16 (56.25%) | 9/16 (56.25%) |
| Protected 40-image maize regression benchmark | 18/40 (45.00%) | 20/40 (50.00%) |

Crop results below combine laboratory and field/web images; they are not population field-accuracy estimates.

| Crop in the 82-file test | Original model | Candidate |
| --- | ---: | ---: |
| Tomato | 36/46 (78.26%) | 30/46 (65.22%) |
| Maize | 21/28 (75.00%) | 20/28 (71.43%) |
| Pepper | 8/8 (100.00%) | 8/8 (100.00%) |

On the separate 40-image benchmark, each maize category has ten source-labeled photos:

| Maize category | Original correct | Candidate correct |
| --- | ---: | ---: |
| Cercospora leaf spot Gray leaf spot | 0/10 | 1/10 |
| Common rust | 8/10 | 7/10 |
| Northern Leaf Blight | 6/10 | 5/10 |
| healthy | 4/10 | 7/10 |

The saved Safetensors checkpoint was loaded again for the 40-image comparison, with its weights and class mapping checked. That comparison calls the actual application `classify()` function with maize selected. The 82-image comparison uses the matching processor and the same crop-restricted ranking without renormalizing the scores. No predictions are mocked, random or supplied from ground truth.

## What this means

The extra training did not produce a reliable replacement. It lost seven correct answers in the combined 82-file check and six in the laboratory replay subset. Its new university maize result stayed at 9/16. It gained two correct answers on the previously observed 40-image benchmark, which is too limited to outweigh the regressions or establish general improvement. Tomato performance declined in this experiment.

Pepper scored 8/8 for both models, but that includes only two field/web bacterial-spot photos and six laboratory photos. It provides no new healthy-bell-pepper field evidence and cannot establish reliable real-world pepper accuracy.

These tests are preliminary development checks. PlantVillage and PlantDoc were already used by the publisher, and the candidate now trains on other university images from the same source as the maize tests. Exact files were held out, but true plant/session separation is not established. Neither the 82-file score nor the 40-file score should be advertised as independently verified system accuracy. Candidate scores are uncalibrated; top-1 classification accuracy here does not measure the accuracy of confidently accepted diagnoses.

## Next useful work

Obtain a larger, expert-reviewed field collection with plant/farm/session identifiers, especially gray leaf spot, healthy maize, healthy bell pepper and the two tomato coverage gaps. Keep a genuinely fresh external test collection inaccessible to training and model selection. The blocked Bangladesh tomato source is worth revisiting through a normal browser/manual download. Source labels and unsupported classes must be reviewed before import.

Future experiments should compare a smaller head-only or partially frozen adaptation against the baseline using validation data, and select training settings before evaluating a fresh test set. The current observed test results are development evidence; repeatedly tuning against them would bias the comparison. Calibrate any promising candidate using validation data before an independently reviewed production replacement.

## Saved records

- [Image manifest](../ai-service/training/field-02/manifest.csv) and [source provenance](../ai-service/training/field-02/provenance.json). Image paths are relative to the original `.model-cache/field-training` directory, not the archived copy.
- [Full metrics and confusion matrices](../ai-service/training/field-02/report.json). Source/crop macro F1 averages classes with actual support in that subset.
- [82 individual predictions](../ai-service/training/field-02/predictions.csv).
- [40-image regression metrics](../ai-service/training/field-02/field-report.json) and [individual predictions](../ai-service/training/field-02/field-predictions.csv).
- [Content-review exclusions](../ai-service/training/field-review-exclusions.json).
- [Training and reproduction instructions](field-training.md).

Images and model weights remain in ignored local cache directories. The candidate is at `ai-service/.model-cache/training-runs/field-02/checkpoint/`. Its model.safetensors SHA-256 is `d5e617a48d927a98079abc91dffc26c297f47d7c89cb67209f279bb818068ce2`. Do not treat this candidate as deployment-ready.

Verification: 23 Python tests ran, 21 passed and two optional model tests were skipped. Separately, the real four-epoch run, 82-file baseline/candidate comparison and saved-checkpoint 40-image application comparison completed. CSV counts were independently checked against both metric reports; the archived image manifest checksum matches the actual training report. No images or model weights are committed.
