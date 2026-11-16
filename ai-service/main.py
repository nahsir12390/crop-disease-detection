import os
from io import BytesIO
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

# Keep Hugging Face downloads inside this project, not a shared user cache.
BASE_DIR = Path(__file__).resolve().parent
os.environ.setdefault("HF_HOME", str(BASE_DIR / ".model-cache"))
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

app = FastAPI(title="Crop Disease Detection AI", version="0.2.0")
MAX_BYTES = 5 * 1024 * 1024
MODEL_ID = "neghani/plantvillage-mobilenetv2"
MODEL_REVISION = "v1.0"
_model = None
_model_error = None
_lock = Lock()


def get_classifier():
    global _model, _model_error
    if _model is not None:
        return _model
    with _lock:
        if _model is not None:
            return _model
        if _model_error is not None:
            raise RuntimeError(_model_error)
        try:
            from transformers import pipeline
            _model = pipeline(
                task="image-classification",
                model=MODEL_ID,
                revision=MODEL_REVISION,
                device=-1,
            )
            return _model
        except Exception as exc:
            _model_error = f"{type(exc).__name__}: {exc}"
            raise RuntimeError(_model_error) from exc


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model_loaded": _model is not None,
        "model": MODEL_ID,
    }


@app.post("/predict")
async def predict(file: UploadFile = File(...)):
    if file.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=422, detail="Upload a JPEG, PNG, or WebP image")
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Image must be 5 MB or smaller")
    try:
        with Image.open(BytesIO(content)) as source:
            source.verify()
        with Image.open(BytesIO(content)) as source:
            image = source.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(status_code=422, detail="Invalid image file")

    try:
        classifier = get_classifier()
        predictions = classifier(image, top_k=3)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Pretrained model unavailable. Check AI service logs and network access.",
        ) from exc

    top = predictions[0]
    confidence = float(top["score"])
    return {
        "label": top["label"] if confidence >= 0.5 else "Uncertain",
        "confidence": confidence,
        "uncertain": confidence < 0.5,
        "top_predictions": [
            {"label": item["label"], "confidence": float(item["score"])}
            for item in predictions
        ],
        "model": MODEL_ID,
    }
