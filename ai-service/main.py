from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from io import BytesIO

app = FastAPI(title="Crop Disease Detection AI", version="0.1.0")
MAX_BYTES = 5 * 1024 * 1024

@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": False}

@app.post("/predict")
async def predict(file: UploadFile = File(...)):
    if file.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=422, detail="Upload a JPEG, PNG, or WebP image")
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Image must be 5 MB or smaller")
    try:
        with Image.open(BytesIO(content)) as image:
            image.verify()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=422, detail="Invalid image file")
    raise HTTPException(status_code=503, detail="Model not trained or loaded yet")
