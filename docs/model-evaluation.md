# Maize disease evaluation: 40 real field photographs

**Preliminary external-dataset test. Not certified independent accuracy verification.**

Run date: 2026-11-16T19:37:53.809326+01:00 (Africa/Lagos). Status: **completed**, 40/40 images processed with real inference; zero download or inference failures in this completed run.

## Simple explanation

We tested **40 real maize photographs**, with 10 in each category. The model's highest-scoring maize class matched the dataset label for **18 images** and was wrong for **22 images**. That is **45.0% top-1 accuracy** on these selected photos. Best category/categories: **Common rust**. Lowest category/categories: **Gray leaf spot**.

The app would mark **12 of 40** images as uncertain. It would show a confident result for **28**, of which **13** were correct (46.4% accuracy on accepted results; 70.0% coverage). A top-ranked match below the app's threshold is counted in top-1 accuracy but is **not** a confirmed app answer. Correct-and-confident results cover 32.5% of all 40 images.

The model called **24 photos Common rust**, but only **8** of those calls matched the dataset label. Its high common-rust hit rate therefore does not mean every rust prediction can be trusted. **Northern leaf blight** had the strongest balance of precision and recall (F1 = 0.667). **15 of the 28 accepted/confident outputs were wrong.** This test does not support relying on the model alone for field diagnosis.

This small test describes these photographs only. It does not establish that the model is reliable for every farm, phone camera, disease stage or background. Ten images per category is a small sample: one mistake changes that category's result by 10 percentage points. A nominal 95% Wilson interval for overall top-1 accuracy is 30.7% to 60.2%; it assumes independent observations and does not account for correlated photos or label errors.

## Dataset selection and label mapping

We investigated [PlantVillage](https://github.com/spMohanty/PlantVillage-Dataset), which has all four requested categories. The deployed model's [training record](https://huggingface.co/neghani/plantvillage-mobilenetv2/blob/77e6d262dca53b818f7ad1d67088700754515639/run_info.json) declares PlantVillage plus Cropped-PlantDoc. Using random PlantVillage images could therefore test training examples, and even its published test split is an in-domain evaluation. PlantDoc also belongs to the training source family and its public class directories do not include a healthy-maize category. The Mendeley [mixed-source corn collection](https://data.mendeley.com/datasets/hmkd6nbngr/1) combines field and public-repository images and does not establish independence; its generic blight label also needs clarification.

Instead, we selected original field photographs from **Hamish Craze, University of Pretoria, Diseases of maize in the field, version 1 (2022)**, DOI [https://doi.org/10.25403/UPresearchdata.20237613.v1](https://doi.org/10.25403/UPresearchdata.20237613.v1), licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The original dataset contains 2,355 maize field photos taken at different times and sites in South Africa. Provenance and annotations were retrieved from its [versioned API](https://api.figshare.com/v2/articles/20237613/versions/1), `Database.csv` and `ReadMe.txt`. Original photographs are used unchanged; no generated images or augmented copies are used.

| Source flag | Report category | Exact supported model label |
| --- | --- | --- |
| NoFoliarSymptoms | Healthy | `Corn_(maize)___healthy` |
| CR | Common rust | `Corn_(maize)___Common_rust_` |
| NCLB | Northern leaf blight | `Corn_(maize)___Northern_Leaf_Blight` |
| GLS | Gray leaf spot | `Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot` |

`NoFoliarSymptoms` is mapped to Healthy because it means no recorded foliar disease symptoms; it is **not** a laboratory confirmation that a plant is free of pathogens. Gray/grey leaf spot is the same dataset category mapped to the model's combined Cercospora/gray leaf spot class. NCLB maps to Northern Leaf Blight. CR maps to Common Rust, never Southern Rust.

The source has multi-label rows. We require **exactly one of all eight annotation flags to be 1**, excluding mixed diseases, PLS, southern rust, Other and unidentified disease. We also require original JPEG size <= 5 MiB and resolution <= 20 megapixels, matching app limits. Files are sorted then shuffled with seed `20261116` and the category flag; the first 10 eligible unique images/class are selected **before inference**. No images are selected or replaced because of a favorable/unfavorable prediction. Selection is reproducible from [the manifest](../ai-service/evaluation/maize-manifest.json). Additional pixel-limit/duplicate exclusions after the file-size prefilter: 0. The manifest records the candidate counts before and after file-size filtering. The upload limits and single-label restriction make this a selected subset, not a random sample of all field photos.

Only selected ZIP entries are fetched through verified HTTP byte ranges; the 10.8 GB archive is not downloaded in full. ZIP CRC, source annotation-file checksums, image SHA-256 and decoded RGB hashes are checked. The 40 selected images have distinct byte hashes and distinct decoded RGB hashes. Near-duplicate leaves or multiple shots of the same plant cannot be excluded.

## Training-overlap investigation

The Pretoria collection is **not listed** among the model's declared PlantVillage/Cropped-PlantDoc training sources. We compared all 40 selected source basenames, case-insensitively, with the **train, validation and test** filenames in both the base v1.0 and deployed v1.1 `splits.json`, and with every file in Cropped-PlantDoc at the exact commit `5467f6012d78d1c446145d5f582da6096f852ae8` declared by v1.1. Number of filename matches: **0**. Complete checks and metadata hashes are in [maize-overlap-audit.json](maize-overlap-audit.json).

This is a filename audit, **not** a full byte or perceptual comparison against every training image. Renamed, re-encoded or web-reused images, undocumented upstream sources, and related leaves cannot be ruled out. Thus this is a **preliminary external-dataset test with no detected filename overlap**, rather than proof that every image is independent. A stronger next evaluation should use newly collected, expert-labeled leaves, separate farms/dates/plants, more samples, and explicit image/plant-level deduplication against training data.

## Exactly what was tested

- Model: `neghani/plantvillage-mobilenetv2`, version `v1.1`, immutable revision `77e6d262dca53b818f7ad1d67088700754515639`.
- Called the **unchanged application's** `main.get_classifier()` once, then `main.classify(original_bytes, "maize")` for each photo. The main.py SHA-256 is `ad17ab65d1dac3c055a6f6cf3b3e257b333fdd0a3bfa4b11b0870d44702cd786`. No duplicated inference pipeline, no mocked model, no tuning or retraining during this evaluation.
- The bundled processor converts the validated/EXIF-oriented image to RGB, resizes the short edge to 256, center-crops to 224x224, rescales by 1/255 and normalizes with mean/std 0.5.
- Publisher temperature `0.8845188130635788` is applied to logits before 38-class softmax. Predictions are ranked only among the four maize labels; full-model probabilities are retained, not normalized to artificially sum to 100% inside maize.
- The app marks scores below `0.5` as uncertain. The top three maize classes and all four-category outcomes are recorded.
- This measures maize disease classification **given that maize was selected**. It does not evaluate automatic crop identification, unsupported disease rejection, non-leaf detection, or HTTP/browser reliability. Laravel's multipart field is `crop=maize`; its rendering does not change the class or confidence.
- Versions: Python 3.12.7, PyTorch 2.6.0+cpu, Transformers 4.57.6, Pillow 12.3.0, NumPy 2.2.6.

## Results by category

| Actual category | Tested | Correct | Wrong | Category accuracy | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Healthy | 10 | 4 | 6 | 40.0% | 0.800 | 0.400 | 0.533 |
| Common rust | 10 | 8 | 2 | 80.0% | 0.333 | 0.800 | 0.471 |
| Northern leaf blight | 10 | 6 | 4 | 60.0% | 0.750 | 0.600 | 0.667 |
| Gray leaf spot | 10 | 0 | 10 | 0.0% | 0.000 | 0.000 | 0.000 |

Category accuracy is correct predictions divided by the 10 actual images in that class, which equals class recall here. Precision asks: of predictions calling a disease, how many were correct? Recall asks: of images labeled with that disease, how many did the model find? F1 balances precision and recall. Scores use the top-ranked maize class for **all** photos, including uncertain ones; zero denominators are defined as 0.

| Averaging | Precision | Recall | F1 |
| --- | ---: | ---: | ---: |
| Macro (equal weight per category) | 0.471 | 0.450 | 0.418 |
| Weighted (by actual class count) | 0.471 | 0.450 | 0.418 |
| Micro (all decisions) | 0.450 | 0.450 | 0.450 |

Top-three recall: **36/40 (90.0%)**. This only means the dataset label was among three suggestions; it is not top-1 accuracy and does not mean the app gave a correct confident answer.

## Confusion matrix

Rows are the **actual dataset label**. Columns are the **predicted maize label**. The diagonal contains correct predictions; other cells show mistakes. All 40 decisions are included.

| Actual / Predicted | Healthy | Common rust | Northern leaf blight | Gray leaf spot |
| --- | ---: | ---: | ---: | ---: |
| Healthy | 4 | 5 | 1 | 0 |
| Common rust | 0 | 8 | 0 | 2 |
| Northern leaf blight | 0 | 3 | 6 | 1 |
| Gray leaf spot | 1 | 8 | 1 | 0 |

## Reproduce and inspect

From the existing Laravel project root, in PowerShell:

```powershell
ai-service/.venv/Scripts/python.exe ai-service/evaluate_maize.py
```

On first execution without the committed manifest, the script selects the fixed seeded sample and caches originals under ignored `ai-service/.model-cache/maize-evaluation/`. With the manifest present, it reuses exactly those images, downloads only missing originals and verifies their checksums. It checks the exact model revision and all four label IDs before inference. Reports are written only after 40 successful predictions. Errors exit nonzero and are recorded in `docs/maize-evaluation-status.json`; do not treat an old completed report as a successful new run after a failure. No global packages are installed. Nothing in Laravel or another mobile project is modified by the evaluation script.

- [Individual predictions CSV](maize-predictions.csv): all 40 source filenames, IDs, ground truth, predictions, confidence, uncertainty, top-three classes and hashes.
- [Metrics JSON](maize-metrics.json): exact numeric metrics, model/software provenance and status.
- [Confusion matrix CSV](maize-confusion-matrix.csv).
- [Source/selection manifest](../ai-service/evaluation/maize-manifest.json): labels, dataset IDs, ZIP members, annotation flags and hashes; images are deliberately not committed.
- [Overlap audit](maize-overlap-audit.json).

**Can we trust it?** We can trust this as a recorded, reproducible result for these 40 source-labeled photos under the current application pipeline. We still need larger, expert-verified, plant-separated independent testing before claiming general real-world accuracy. Confidence percentages are model scores, not guarantees that a diagnosis is correct.
