<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Crop Disease Detection</title>
    @vite(['resources/css/app.css', 'resources/js/app.js'])
</head>
<body class="min-h-screen bg-emerald-50 text-slate-900">
    <header class="bg-emerald-900 px-6 py-5 text-white">
        <div class="mx-auto max-w-4xl"><h1 class="text-2xl font-bold">Crop Disease Detection</h1><p class="text-emerald-100">Deep learning research prototype</p></div>
    </header>
    <main class="mx-auto max-w-4xl px-4 py-12">
        <section class="rounded-2xl bg-white p-6 shadow-sm sm:p-10">
            <h2 class="text-2xl font-semibold">Analyze a crop leaf</h2>
            <p class="mt-2 text-slate-600">Upload a clear JPG, PNG, or WebP image (maximum 5 MB). Predictions will be available after model training and evaluation.</p>
            @if(session('notice'))
                <div role="status" class="mt-5 rounded-lg bg-amber-50 p-4 text-amber-900">{{ session('notice') }}</div>
            @endif
            @if($errors->any())
                <div role="alert" class="mt-5 rounded-lg bg-red-50 p-4 text-red-800">{{ $errors->first() }}</div>
            @endif
            @if(session('prediction'))
                <div role="status" class="mt-5 rounded-lg bg-emerald-50 p-4 text-emerald-900">
                    <strong>Prediction:</strong> {{ session('prediction')['label'] ?? 'Unknown' }}
                    @if(isset(session('prediction')['confidence']))
                        ({{ round(session('prediction')['confidence'] * 100, 1) }}% confidence)
                    @endif
                </div>
            @endif
            <form action="{{ route('detect.analyze') }}" method="POST" enctype="multipart/form-data" class="mt-8 space-y-5">
                @csrf
                <label for="image" class="block font-medium">Leaf image</label>
                <input id="image" name="image" type="file" accept="image/jpeg,image/png,image/webp" required class="block w-full rounded-lg border border-slate-300 p-3" />
                <img id="preview" alt="Selected crop leaf" class="hidden max-h-80 w-full rounded-lg object-contain" />
                <button type="submit" class="rounded-lg bg-emerald-800 px-6 py-3 font-semibold text-white hover:bg-emerald-900">Analyze leaf</button>
            </form>
            <p class="mt-6 text-sm text-slate-500">Research demonstration only. Do not make treatment decisions from an unverified model prediction.</p>
        </section>
    </main>
    <script>
        const input = document.getElementById('image');
        const preview = document.getElementById('preview');
        let objectUrl;
        input.addEventListener('change', () => {
            if (objectUrl) URL.revokeObjectURL(objectUrl);
            preview.classList.add('hidden');
            const file = input.files[0];
            if (!file || !['image/jpeg','image/png','image/webp'].includes(file.type)) return;
            objectUrl = URL.createObjectURL(file);
            preview.src = objectUrl;
            preview.classList.remove('hidden');
        });
    </script>
</body>
</html>
