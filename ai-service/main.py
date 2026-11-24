import asyncio
import logging
import json
import math
import os
import warnings
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

BASE_DIR = Path(__file__).resolve().parent
os.environ.setdefault("HF_HOME", str(BASE_DIR / ".model-cache"))
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
logger = logging.getLogger("uvicorn.error")
MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 20_000_000
CROPS = json.loads((BASE_DIR / 'crops.json').read_text(encoding='utf-8'))
CROP_PREFIXES = {key: value['prefix'] for key, value in CROPS.items()}


def validate_crop(crop):
    if crop == "cassava":
        raise HTTPException(422, "Cassava is not supported by the current model. Choose a crop listed in the portal.")
    if crop not in CROP_PREFIXES:
        raise HTTPException(422, "Choose a supported crop listed in the portal")

MODEL_ID = "neghani/plantvillage-mobilenetv2"
# Field-fine-tuned v1.1 snapshot, with its matching processor and calibration.
MODEL_REVISION = "77e6d262dca53b818f7ad1d67088700754515639"
MODEL_VERSION = "v1.1"
_temperature = 1.0
_confidence_threshold = 0.5
_model = None
_processor = None
_model_error = None
_status = "loading"
_lock = Lock()
_inference_lock = Lock()


def get_classifier():
    global _model, _processor, _model_error, _status, _temperature, _confidence_threshold
    if _model is not None:
        return _model
    with _lock:
        if _model is not None:
            return _model
        _status = "loading"
        try:
            import torch
            from huggingface_hub import hf_hub_download
            from transformers import AutoModelForImageClassification, AutoImageProcessor
            options = {"revision": MODEL_REVISION, "trust_remote_code": False}
            processor = AutoImageProcessor.from_pretrained(MODEL_ID, use_fast=False, **options)
            model, info = AutoModelForImageClassification.from_pretrained(
                MODEL_ID, use_safetensors=True, output_loading_info=True, **options
            )
            if info.get("missing_keys") or info.get("unexpected_keys") or info.get("mismatched_keys"):
                raise RuntimeError(f"Incompatible model weights: {info}")
            labels = model.config.id2label
            if len(labels) != 38 or any("___" not in label for label in labels.values()):
                raise RuntimeError("Model does not contain the expected PlantVillage labels")
            configured = [label for crop in CROPS.values() for label in crop['classes']]
            if len(configured) != len(set(configured)) or set(configured) != set(labels.values()):
                raise RuntimeError('Crop catalogue does not exactly match the loaded model classes')
            if any(not label.startswith(crop['prefix']) for crop in CROPS.values() for label in crop['classes']):
                raise RuntimeError('Crop catalogue contains an invalid class prefix')
            calibration_path = hf_hub_download(MODEL_ID, "calibration.json", revision=MODEL_REVISION)
            threshold_path = hf_hub_download(MODEL_ID, "threshold.json", revision=MODEL_REVISION)
            temperature, threshold = calibration_settings(
                json.loads(Path(calibration_path).read_text()), json.loads(Path(threshold_path).read_text())
            )
            model.eval()
            # Check preprocessing and a forward pass before declaring readiness.
            with torch.inference_mode():
                output = model(**processor(images=Image.new("RGB", (256, 256)), return_tensors="pt"))
            if output.logits.shape != (1, 38) or not torch.isfinite(output.logits).all():
                raise RuntimeError("Model warm-up produced invalid logits")
            _temperature, _confidence_threshold = temperature, threshold
            _processor, _model = processor, model
            _model_error, _status = None, "ready"
            logger.info("Model ready: %s revision %s", MODEL_ID, MODEL_REVISION)
            return _model
        except Exception as exc:
            _model_error = f"{type(exc).__name__}: {exc}"
            _status = "error"
            logger.exception("Model initialization failed: %s", MODEL_ID)
            raise


@asynccontextmanager
async def lifespan(app):
    async def initialize():
        try:
            await run_in_threadpool(get_classifier)
        except Exception:
            pass  # Full traceback logged by get_classifier; health remains available.
    task = asyncio.create_task(initialize())
    yield
    await task


app = FastAPI(title="Crop Disease Detection AI", version="0.3.0", lifespan=lifespan)


def calibration_settings(calibration, threshold):
    temperature = float(calibration["temperature"])
    confidence_threshold = float(threshold["threshold"])
    if not math.isfinite(temperature) or temperature <= 0:
        raise ValueError("Invalid model calibration temperature")
    if not math.isfinite(confidence_threshold) or not 0 < confidence_threshold < 1:
        raise ValueError("Invalid model confidence threshold")
    if threshold.get("status") != "selected":
        raise ValueError("Model confidence threshold has not been selected")
    if not math.isclose(float(threshold["temperature"]), temperature):
        raise ValueError("Model threshold and calibration temperatures disagree")
    return temperature, confidence_threshold


@app.get("/health")
def health():
    return {
        "status": _status,
        "model_loaded": _model is not None,
        "model": MODEL_ID,
        "revision": MODEL_REVISION,
        "model_version": MODEL_VERSION,
        "supported_crops": {key: spec['label'] for key, spec in CROPS.items()},
        "temperature": _temperature if _model is not None else None,
        "confidence_threshold": _confidence_threshold if _model is not None else None,
        "error": "Model initialization failed; inspect the AI service logs and restart after fixing the cause." if _model_error else None,
    }


def readable_prediction(label, confidence):
    crop, disease = label.split("___", 1)
    crop = " ".join(crop.replace("_", " ").split())
    disease = " ".join(disease.replace("_", " ").split())
    disease = disease[0].upper() + disease[1:]
    return {"label": label, "display_label": f"{crop} - {disease}", "crop": crop,
            "disease": disease, "confidence": confidence}


def classify(content, crop):
    validate_crop(crop)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"}:
                    raise HTTPException(422, "Upload a JPEG, PNG, or WebP image")
                if source.width * source.height > MAX_PIXELS:
                    raise HTTPException(422, "Image resolution is too large; use an image under 20 megapixels")
                if getattr(source, "is_animated", False):
                    raise HTTPException(422, "Upload a still image rather than an animation")
                source.verify()
            with Image.open(BytesIO(content)) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise HTTPException(422, "Invalid or unsafe image file") from exc

    if _model is None:
        message = "The model is downloading or initializing. Please try again shortly." if _status == "loading" else "The model could not load. Please contact the administrator or try again after the AI service is restarted."
        raise HTTPException(503, message, headers={"Retry-After": "10"})
    try:
        import torch
        with _inference_lock, torch.inference_mode():
            inputs = _processor(images=image, return_tensors="pt")
            scores = (_model(**inputs).logits / _temperature).softmax(dim=-1)[0]
            # Preserve the original probabilities: filtering must not inflate confidence.
            allowed = [i for i, label in _model.config.id2label.items() if label.startswith(CROP_PREFIXES[crop])]
            if not allowed:
                raise RuntimeError(f"No model classes available for {crop}")
            values, positions = scores[allowed].topk(min(3, len(allowed)))
            indices = [allowed[int(position)] for position in positions]
            crop_conflict = int(scores.argmax()) not in allowed
            crop_confidence = float(scores[allowed].sum())
        predictions = [readable_prediction(_model.config.id2label[int(i)], float(v)) for v, i in zip(values, indices)]
        limited = CROPS[crop]['coverage'] != 'healthy_and_diseases'
        uncertain = limited or predictions[0]["confidence"] < _confidence_threshold
        return {**predictions[0], "uncertain": uncertain,
                "limited_coverage": limited, "coverage_note": CROPS[crop]['note'],
                "uncertainty_reason": ("limited_coverage" if limited else "crop_conflict" if crop_conflict else "low_confidence") if uncertain else None,
                "selected_crop_confidence": crop_confidence,
                "top_predictions": predictions, "selected_crop": crop,
                "model": MODEL_ID, "revision": MODEL_REVISION, "model_version": MODEL_VERSION,
                "confidence_threshold": _confidence_threshold}
    except Exception as exc:
        logger.exception("Image inference failed")
        raise HTTPException(500, "Image analysis failed. Please try another clear leaf image.") from exc


@app.post("/predict")
async def predict(file: UploadFile = File(...), crop: str = Form(...)):
    try:
        validate_crop(crop)
        if file.content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise HTTPException(422, "Upload a JPEG, PNG, or WebP image")
        content = await file.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise HTTPException(413, "Image must be 5 MB or smaller")
        return await run_in_threadpool(classify, content, crop)
    finally:
        await file.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    get_classifier()
    print("Model loaded and warm-up completed. Cached files are ready for the API.")
