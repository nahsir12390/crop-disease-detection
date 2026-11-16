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
        <div class="mx-auto max-w-4xl"><h1 class="text-2xl font-bold">Crop Disease Detection</h1><p class="text-emerald-100">Pretrained MobileNetV2 leaf analysis</p></div>
    </header>
    <main class="mx-auto max-w-4xl px-4 py-12">
        <section class="rounded-2xl bg-white p-6 shadow-sm sm:p-10">
            <h2 class="text-2xl font-semibold">Analyze a crop leaf</h2>
            <p class="mt-2 text-slate-600">Upload a clear image of one leaf. JPG, PNG or WebP, up to 5 MB. Initial model supports PlantVillage classes; cassava support is planned separately.</p>
            @if(session('notice'))
                <div role="status" class="mt-5 rounded-lg bg-amber-50 p-4 text-amber-900">{{ session('notice') }}</div>
            @endif
            @if($errors->any())
                <div role="alert" class="mt-5 rounded-lg bg-red-50 p-4 text-red-800">{{ $errors->first() }}</div>
            @endif
            @if(session('prediction'))
                @php($result = session('prediction'))
                <div role="status" class="mt-5 rounded-lg bg-emerald-50 p-5 text-emerald-950">
                    <h3 class="text-lg font-semibold">Analysis result</h3>
                    <p class="mt-2"><strong>Prediction:</strong> {{ str_replace(['___', '_'], [' — ', ' '], $result['label'] ?? 'Unknown') }}</p>
                    @if(isset($result['confidence']))
                        <p><strong>Model confidence:</strong> {{ round($result['confidence'] * 100, 1) }}%</p>
                    @endif
                    @if($result['uncertain'] ?? false)
                        <p class="mt-2 font-medium">Uncertain result — try a clearer image or seek expert advice.</p>
                    @endif
                    @if(!empty($result['top_predictions']))
                        <h4 class="mt-4 font-semibold">Top matches</h4>
                        <ul class="mt-2 list-disc space-y-1 pl-5">
                            @foreach($result['top_predictions'] as $match)
                                <li>{{ str_replace(['___', '_'], [' — ', ' '], $match['label']) }} — {{ round($match['confidence'] * 100, 1) }}%</li>
                            @endforeach
                        </ul>
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
            <p class="mt-6 text-sm text-slate-500">Results are predictions, not a confirmed diagnosis. The model may perform poorly on field photographs.</p>
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
