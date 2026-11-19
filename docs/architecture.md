# Architecture and academic alignment

Laravel 12 provides the web UI and validates uploads. It sends images over HTTP to a Python FastAPI service on port 8001. FastAPI verifies the image and will eventually load a trained TensorFlow/Keras model.

Current status: **no trained model, no genuine predictions, and no measured accuracy**. The API intentionally returns HTTP 503 for valid images until a model is integrated.

Proposed Chapter Three changes **require supervisor approval**:
- Replace Flask as the application-serving layer with Laravel (PHP) plus a separate Python FastAPI inference API.
- Update the system architecture diagram and communication/data flow.
- Add PHP, Composer, Laravel, Node/Vite, FastAPI, and MySQL to the technology and software requirements sections.
- Explain upload validation, API error handling, privacy, and secure prediction-history storage.
- Preserve the research's custom CNN vs MobileNetV2 training and evaluation methodology.

Do not present previously drafted accuracy values as actual experimental results without reproducible training and evaluation.
