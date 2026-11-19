# Field-photo training experiment

This extends the existing training tools; Laravel and the deployed model are unchanged. The objective is to adapt MobileNetV2 to a small mixed collection of field/web photographs while retaining examples for every currently supported Tomato, Maize and Bell Pepper class.

The completed experiment's [actual results](field-training-results.md) show a regression in the combined held-out check. Its candidate was not deployed.

## Source review

| Source | Labels and suitability | Terms/access | Decision |
| --- | --- | --- | --- |
| [University of Pretoria: Diseases of maize in the field](https://doi.org/10.25403/UPresearchdata.20237613.v1) | Single-label common rust, northern corn leaf blight, gray leaf spot and no visible foliar symptoms map to the four model maize classes. Multi-label/other disease examples excluded. | CC BY 4.0; Hamish Craze. ZIP entries downloaded individually with HTTP byte ranges; metadata and image checksums checked. | Use additional photos outside the protected benchmark. This becomes an adaptation-source dataset for the candidate, not an independent external dataset. |
| [Cropped-PlantDoc](https://github.com/pratikkayal/PlantDoc-Dataset) | Non-laboratory, internet-collected images; eight tomato and one bell pepper disease folder map to model labels. These are source annotations, not new expert verification. | CC BY 4.0; Davinder Singh, Naman Jain, Pranjali Jain, Pratik Kayal, Sudhakar Kumawat and Nipun Batra. Pinned commit `5467f6012d78d1c446145d5f582da6096f852ae8`, original Git blob hashes checked. | Training supplement. Healthy pepper folder excluded after apparent black-pepper crop mismatches were observed. Publisher v1.1 already used PlantDoc, so its test results cannot demonstrate independence. Original test images stay out of our training/validation. |
| [PlantVillage](https://github.com/spMohanty/PlantVillage-Dataset) | Controlled-background photographs covering all 16 supported classes. | Reuse the previous locally cached, pinned pilot collection and its recorded source groups. | Replay examples with previous splits preserved. Not independent evidence. |
| [Tomato Leaf Disease Classification Dataset](https://data.mendeley.com/datasets/jttrv2w27r/1) | Dataset authors describe field collection across Bangladesh in March 2025. Five categories match: bacterial spot, yellow leaf curl virus, early blight, healthy and late blight. Leaf-miner damage and magnesium deficiency do not match supported classes. | CC BY 4.0; Nure Alam Siddiki Rachin, Nasim Mahmud Likhon and Md Abdullah Hel Baki. Direct page/API download attempts from local Python returned HTTP 403. | Promising next source, **not downloaded or trained on in this run**. No accuracy claims. |
| [Pepper Bell Leaf Disease](https://data.mendeley.com/datasets/w9drvtxg9g/1) | Bacterial spot/healthy match, but four other categories do not. The landing page does not establish field capture conditions or plant-level grouping. | CC BY 4.0; Roughten Elvsava. | Investigated, not included pending source/image review. Do not describe it as verified independent field data. |
| [PlantWild/v2](https://tqwei05.github.io/PlantWild/) | Broad in-the-wild categories; further taxonomy and overlap review needed. | Author page specifies CC BY-NC-ND 4.0; multi-GB archives. | Not included in this run. Review terms and intended redistribution before any future use. |

The original model's [publisher documentation](https://huggingface.co/neghani/plantvillage-mobilenetv2) declares PlantVillage and Cropped-PlantDoc training. The university dataset is not a declared source, but undisclosed overlap, renamed/recompressed copies and web reuse cannot be ruled out. None of these checks certify independence.

## Reproduce data preparation

First restore the existing 40-image benchmark and the previous PlantVillage pilot following [evaluation instructions](model-evaluation.md) and [training instructions](model-training.md). Then run from the repository root:

```powershell
.\ai-service\.venv\Scripts\python.exe ai-service/prepare_field_training.py
```

The builder targets 20 new university photographs per maize class (12 training, 4 validation, 4 test), plus 12 PlantDoc photographs per mapped class (8 training, 2 validation, 2 test), and preserves the 288-image replay collection. The nine mapped PlantDoc classes give a target of 476 images overall: 312 training, 82 validation and 82 test. A failed count/download stops preparation; partial cached images are not a completed dataset. The final manifest and provenance give actual counts and exclusions. Nothing is selected by whether the model predicts it correctly.

Data stays under ignored `ai-service/.model-cache/`. The generated CSV paths are relative to its original location, `.model-cache/field-training/manifest.csv`; archived copies are records, not relocated datasets.

Safeguards:

- Exclude all 40 protected benchmark photos, exact decoded copies and dHash near matches.
- Exclude related benchmark leaf/minute groups inferred from university filenames. These are heuristics; verified plant IDs are unavailable.
- Reject cross-split inferred groups, exact duplicates and new near-duplicate candidates before inference. Near duplicate uses a 64-bit horizontal dHash with distance at most four, which can both miss copies and reject distinct similar leaves. Existing replay splits retain their previous group/duplicate limitations.
- Check original bytes/checksums, labels, supported file formats, the 5 MiB upload limit and 20-megapixel limit. No disease labels are invented or inferred from the model.
- Keep PlantDoc's original test partition out of training/validation. Generic source filenames do not prove distinct plants. Internet annotations can be noisy, so expert review remains necessary.
- A contact-sheet review excluded apparent mixed-crop healthy-pepper examples, infographics, multi-panel collages and a fruit-focused example before the final completed experiment. The source URLs and reasons are recorded in `ai-service/training/field-review-exclusions.json`. Replacements follow the same seeded ordering and image checks. This is content screening, not expert disease verification.

**Coverage gaps:** new field data covers all four maize classes, eight tomato classes and bell pepper bacterial spot. Tomato Target Spot, Spider Mites and healthy bell pepper have replay images only. The PlantDoc spider-mite and mixed-crop healthy-pepper folders were not used without further verification. "No foliar symptoms" is the university source's label mapped to healthy; it does not establish that the whole plant is disease-free.

## Training and testing

The planned single experiment fine-tunes all layers at a small learning rate for four epochs, using validation macro F1 to choose the saved checkpoint:

```powershell
.\ai-service\.venv\Scripts\python.exe ai-service/train_model.py --manifest ai-service/.model-cache/field-training/manifest.csv --output ai-service/.model-cache/training-runs/field-02 --epochs 4 --batch-size 8 --lr 0.00001 --unfreeze
```

Use a new output directory if one exists. Test predictions are not used to select epochs. Reports now separate results by crop and origin so replay scores cannot hide weak field results. Their macro F1 averages classes with actual support in that subset. All other supported class predictions remain represented in confusion matrices.

After training, compare the saved checkpoint to the original on the protected benchmark:

```powershell
.\ai-service\.venv\Scripts\python.exe ai-service/evaluate_candidate.py --checkpoint ai-service/.model-cache/training-runs/field-02/checkpoint --output ai-service/.model-cache/training-runs/field-02/field-regression
```

This is an observed regression benchmark from the same source now used for adaptation. Even if it improves, it is not a new blind, farm-separated external accuracy test. Do not repeatedly tune against it. Candidate confidence remains uncalibrated; calibration and uncertainty evaluation must use validation data, followed by a genuinely new independent collection before a production replacement is justified.

No cloud GPU jobs, global Python installations or automatic production-model replacements are performed. The source model remains pinned until a separately reviewed deployment change.

An initial `field-01` attempt was stopped while the replacement-photo content review was being completed: one more collage was found. It is marked aborted, has no reported experiment results, and must not be used as a completed model. The finalized collection and fixed training settings are used for `field-02`; data exclusions were based on image content, not prediction outcomes.
