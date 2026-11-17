# Training the crop model

The training scripts extend the existing AI service. They do not change Laravel, the deployed model revision, or another project. No new Python packages are required. Run commands from the project root with its existing Python 3.12 virtual environment.

The first real run is complete. See [its results and limitations](model-training-results.md): the pipeline works, but field accuracy did not improve, so its candidate was not deployed.

## First: a small all-crop pilot

```powershell
.\ai-service\.venv\Scripts\python.exe ai-service/prepare_training.py --train-per-class 12 --holdout-per-class 3
.\ai-service\.venv\Scripts\python.exe ai-service/train_model.py --manifest ai-service/.model-cache/training-pilot/manifest.csv --output ai-service/.model-cache/training-runs/pilot-01 --epochs 2 --batch-size 8
```

This selects 288 real PlantVillage images from a pinned public repository: 192 training, 48 validation and 48 test images across 16 classes (10 tomato, 4 maize, 2 bell pepper). Downloads are resumable by rerunning preparation; files already present are reused. A failed download aborts preparation. Images, cached source trees and model weights stay in the ignored `.model-cache` directory. Never commit them.

**This is a pipeline pilot, not independent accuracy verification.** The original model was trained on PlantVillage, so even the pilot's test images may already have been seen by the original model. Selection takes one photograph per source leaf-map group where available. Unmapped images use the source identifier, and their number is recorded in provenance. Unknown plant/session identities and near duplicates remain limitations. Do not advertise its accuracy as real-world performance. Source: https://github.com/spMohanty/PlantVillage-Dataset (revision recorded in provenance). Consult the source's current license and attribution terms before redistributing photographs; this project does not bundle them.

## Training with better field photographs

Use correctly labeled real photos from several plants, farms, camera types, lighting conditions and disease severities. Have ambiguous disease labels reviewed by an agricultural expert. Include healthy leaves and visually similar diseases. A useful starting target is hundreds of varied photographs per class; the amount needed depends on image quality and diversity. The current 40-image field benchmark must remain outside training and validation. Its existing report is unchanged.

Create a CSV with these columns:

```csv
path,label,split,group,source,sha256
images/leaf001.jpg,Tomato___Early_blight,train,farmA-plant001,Your collection with permission,ACTUAL_FILE_SHA256
```

Use the exact model labels, not display names. The pilot manifest lists all 16 supported labels. Supply all classes for each selected crop, with every class represented in train, validation and test. Paths are relative to the CSV. `sha256` may be blank for a custom collection; supplying the actual checksum is preferable. Never copy the placeholder above as a real checksum. `group` must identify the same plant or acquisition session across related photographs: put the whole group in one split. Do not randomly split photographs of the same leaf between train and test. Keep a record of permissions, collection dates and label review. Cassava is not added by this workflow.

Use approximately 70% training, 15% validation and 15% test, while keeping groups together and class coverage balanced. Exact decoded duplicates and group overlap are rejected by the script. This does not detect every near duplicate; manually audit related photographs. Supply `provenance.json` beside the CSV describing origin, license, labeling, grouping and any suspected overlap with pretrained data. That provenance is copied into the report.

Run with a new output directory for each experiment. Defaults train only the classifier head and preserve the frozen backbone's batch-normalization statistics. `--unfreeze --lr 0.00001` allows backbone fine-tuning after a successful head-only experiment, but can overfit and costs more compute. Model input processing comes from the exact processor used in the app; horizontal mirroring is used only during training. The 38-class output and original class ordering are preserved.

## Understanding the output

- `checkpoint/`: saved Safetensors weights, config and image processor.
- `report.json`: baseline and candidate test accuracy, per-class precision/recall/F1, confusion matrices, validation history, source model, counts, manifest checksum and provenance.
- `predictions.csv`: each test image's expected label, baseline prediction, candidate prediction and candidate score.
- `status.json`: `completed` only after the full run finishes. A running status after an error is incomplete, not a successful experiment.

The best epoch is selected using validation macro F1, never test performance. Test predictions use the app's crop restriction without renormalizing probabilities. Baseline uses the publisher temperature; candidate scores use temperature 1 and are **uncalibrated**. Confidence calibration and uncertainty thresholds need to be fitted on validation data before integration; do not reuse the publisher's calibration for new weights. Report accuracy and uncertain/abstention behavior separately in a deployment evaluation.

Do not repeatedly tune against the same test set. Obtain a fresh, expert-reviewed field test set for final comparison, and check all three crops for regressions. A high lab-image score is insufficient evidence of field improvement. Keep the current model until the candidate shows worthwhile gains under independent testing. Uploading a photo to the website never automatically trains it.

Training is a separate local/GPU task, not part of Render startup. The saved candidate is intentionally not loaded by production. Integrating it requires a reviewed model artifact, fresh calibration, compatible labels/processor, warm-up checks and an explicit deployment change. No paid GPU or cloud job is started by these scripts.

Technical references: https://docs.pytorch.org/tutorials/beginner/transfer_learning_tutorial and https://huggingface.co/docs/transformers/tasks/image_classification.
