<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#064e3b">
    <title>Crop Disease Detection | Leaf analysis</title>
    @vite(['resources/css/app.css', 'resources/js/app.js'])
</head>
<body class="min-h-screen bg-stone-50 text-slate-900 antialiased">
    @include('partials.navigation')
    <main class="mx-auto max-w-6xl px-5 py-10 sm:px-8 sm:py-16">
        <div class="mb-10 max-w-3xl">
            <p class="text-xs font-bold uppercase tracking-[0.2em] text-emerald-700">A closer look at crop health</p>
            <h1 class="mt-4 text-4xl font-semibold leading-tight tracking-tight text-emerald-950 sm:text-5xl">One leaf. A clearer picture.</h1>
            <p class="mt-5 max-w-2xl text-lg leading-relaxed text-slate-600">Upload a leaf photo to explore possible crop diseases with a pretrained MobileNetV2 model.</p>
        </div>
        @if($errors->any())
            <div role="alert" class="mb-6 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{{ $errors->first() }}</div>
        @endif
        <div id="client-error" role="alert" class="mb-6 hidden rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"></div>
        <div class="grid items-start gap-7 lg:grid-cols-5">
            <section id="analyze" class="rounded-3xl border border-stone-200 bg-white p-6 shadow-sm sm:p-8 lg:col-span-3">
                <div class="flex items-center justify-between gap-3"><h2 class="text-xl font-semibold text-emerald-950">Analyze your leaf</h2><span class="rounded-full bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-800">Image classification</span></div>
                <p class="mt-2 text-sm leading-6 text-slate-500">Choose a clear photo of a single leaf to get started.</p>
                <form id="analysis-form" action="{{ route('detect.analyze') }}" method="POST" enctype="multipart/form-data" class="mt-6">
                    @csrf
                    <label for="crop" class="block text-sm font-semibold text-emerald-950">1. Choose your crop</label>
                    <select id="crop" name="crop" required aria-describedby="crop-help" class="mt-2 w-full rounded-xl border border-stone-300 bg-white p-3 text-slate-900 focus:ring-2 focus:ring-emerald-600">
                        <option value="">Select a crop</option>
                        @foreach(config('crops') as $key => $crop)
                            <option value="{{ $key }}" @selected(old('crop') === $key)>{{ $crop['label'] }}{{ $crop['coverage'] !== 'healthy_and_diseases' ? ' â€” limited coverage' : '' }}</option>
                        @endforeach
                    </select>
                    <p id="crop-help" aria-live="polite" class="mb-5 mt-2 text-sm text-slate-500">Choose a supported crop before uploading. Pepper supports bell pepper only.</p>
                    <details class="mb-5 rounded-xl border border-stone-200 p-3 text-sm"><summary class="cursor-pointer font-semibold text-emerald-900">Model classes for your selected crop</summary><ul id="crop-classes" class="mt-3 list-inside list-disc space-y-1 text-slate-600"><li>Choose a crop to see its classes.</li></ul></details>
                    <p class="mb-2 text-sm font-semibold text-emerald-950">2. Upload a leaf image</p>
                    <label id="dropzone" for="image" class="relative flex min-h-64 cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed border-emerald-200 bg-emerald-50/40 p-6 text-center transition hover:border-emerald-600 focus-within:ring-2 focus-within:ring-emerald-600">
                        <svg class="mb-4 h-10 w-10 text-emerald-700" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M12 16V3m-5 5 5-5 5 5M4 15v5h16v-5"/></svg>
                        <span class="font-semibold text-emerald-950">Drop your leaf image here</span>
                        <span class="mt-1 text-sm text-slate-500">or tap to browse your files</span>
                        <span class="mt-4 text-xs text-slate-500">JPEG, PNG or WebP · Up to 5 MB</span>
                        <input id="image" name="image" type="file" accept="image/jpeg,image/png,image/webp" required class="sr-only" aria-describedby="file-info" />
                    </label>
                    <p id="file-info" class="mt-3 break-all text-sm text-slate-500" aria-live="polite">No image selected</p>
                    <img id="preview" alt="Selected crop leaf" class="mt-4 hidden max-h-72 w-full rounded-xl bg-stone-100 object-contain" />
                    <button id="submit-button" type="submit" class="mt-6 flex w-full items-center justify-center gap-3 rounded-xl bg-emerald-900 px-6 py-4 font-semibold text-white transition hover:bg-emerald-800 disabled:cursor-wait disabled:opacity-70">
                        <svg id="spinner" class="hidden h-5 w-5 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="3" opacity=".3"/><path d="M12 3a9 9 0 0 1 9 9" stroke="currentColor" stroke-width="3"/></svg><span id="button-label">Analyze leaf</span>
                    </button>
                    <p id="progress" role="status" class="mt-3 text-center text-sm text-emerald-800"></p>
                </form>
            </section>
            <aside class="space-y-6 lg:col-span-2">
                @if(session('prediction'))
                    @php($result = session('prediction'))
                    <section role="status" class="overflow-hidden rounded-3xl border border-emerald-200 bg-white shadow-sm">
                        <div class="bg-emerald-900 p-6 text-white"><p class="text-xs font-semibold uppercase tracking-widest text-emerald-200">Analysis complete</p><h2 class="mt-2 text-2xl font-semibold">{{ $result['uncertain'] ? 'Unable to identify confidently' : $result['disease'] }}</h2><p class="mt-1 text-emerald-100">{{ $result['crop'] }}</p></div>
                        <div class="p-6">
                            <div class="flex items-end justify-between gap-3"><span class="text-sm text-slate-500">{{ $result['uncertain'] ? 'Highest score for your crop' : 'Model confidence' }}</span><strong class="text-3xl text-emerald-900">{{ $result['confidence'] > 0 && $result['confidence'] < 0.0001 ? '<0.01' : number_format($result['confidence'] * 100, 2) }}<span class="text-lg">%</span></strong></div>
                            @if($result['uncertain'])
                                <div class="mt-4 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">
                                    @if($result['limited_coverage'] ?? false)
                                        <p class="font-semibold">Limited model coverage</p><p class="mt-2">{{ $result['coverage_note'] }}</p>
                                    @elseif(($result['uncertainty_reason'] ?? null) === 'crop_conflict')
                                        <p>The model's strongest match is outside your selected crop. This does not mean you chose the wrong crop: the model can misclassify field photos.</p>
                                    @else
                                        <p>The model could not confidently identify a condition for this crop.</p>
                                    @endif
                                    <p class="mt-2">The scores below are tentative matches, not a diagnosis. Try a close-up of one leaf against a plain background or ask an agricultural expert to confirm.</p>
                                </div>
                            @endif
                            <h3 class="mt-6 text-sm font-semibold">Top {{ count($result['top_predictions']) }} possible matches for your crop{{ $result['uncertain'] ? ' (unconfirmed)' : '' }}</h3>
                            <p class="mt-2 text-xs leading-5 text-slate-500">Scores retain the model's original confidence across all classes. They may total less than 100% because other crops are excluded.@if(($result['selected_crop'] ?? '') === 'pepper') Pepper has two supported classes.@endif</p>
                            <ol class="mt-3 divide-y divide-stone-100">
                                @foreach($result['top_predictions'] as $match)
                                    <li class="flex items-start justify-between gap-4 py-3 text-sm"><span class="text-slate-600">{{ $match['display_label'] }}</span><strong class="shrink-0 text-emerald-900">{{ $match['confidence'] > 0 && $match['confidence'] < 0.0001 ? '<0.01' : number_format($match['confidence'] * 100, 2) }}%</strong></li>
                                @endforeach
                            </ol>
                            @if(isset($result['model_version']))
                                <p class="mt-4 border-t border-stone-100 pt-3 text-xs text-slate-500">MobileNetV2 {{ $result['model_version'] }} · Field-image fine-tuning · Publisher-calibrated scores</p>
                            @endif
                        </div>
                    </section>
                @else
                    <section class="rounded-3xl bg-emerald-950 p-7 text-white"><p class="text-xs font-semibold uppercase tracking-widest text-emerald-300">From image to insight</p><h2 class="mt-3 text-2xl font-semibold">Your results appear here.</h2><p class="mt-3 text-sm leading-7 text-emerald-100">See possible leaf conditions and confidence scores for your selected crop. Up to three supported matches appear after analysis.</p><div class="mt-6 flex gap-6 border-t border-white/15 pt-5"><p><strong class="text-2xl">38</strong><span class="block text-xs text-emerald-200">Supported classes</span></p><p><strong class="text-2xl">14</strong><span class="block text-xs text-emerald-200">Supported crops</span></p></div></section>
                @endif
                <section id="guidance" class="rounded-3xl border border-stone-200 bg-white p-6">
                    <h2 class="font-semibold text-emerald-950">Give your photo the best chance</h2>
                    <ul class="mt-4 space-y-3 text-sm leading-6 text-slate-600"><li>Use natural light and keep the leaf in focus.</li><li>Center one leaf against a simple background.</li><li>Show the affected area without covering the leaf.</li></ul>
                    <p class="mt-5 border-t border-stone-100 pt-4 text-xs leading-6 text-slate-500">Choose from 14 crops and review the listed classes before analysis. Some crops have limited coverage. Cassava, rice and other unlisted crops are not supported. The model can misclassify unsupported plants or non-leaf images.</p>
                </section>
            </aside>
        </div>
        <p class="mt-8 max-w-3xl text-xs leading-6 text-slate-500">Predictions are not a confirmed diagnosis. Confidence is a model score, not a guarantee of accuracy. Performance can be lower on field photographs. Confirm findings with an agricultural expert before making crop management decisions.</p>
    </main>
    <footer class="border-t border-stone-200 px-5 py-6 text-center text-xs text-slate-500">Crop Disease Detection Using Deep Learning Technique · Powered by MobileNetV2</footer>
    <script>
        const cropCatalogue = @json(config('crops'));
        const form = document.getElementById('analysis-form');
        const input = document.getElementById('image');
        const crop = document.getElementById('crop');
        const preview = document.getElementById('preview');
        const dropzone = document.getElementById('dropzone');
        const error = document.getElementById('client-error');
        const button = document.getElementById('submit-button');
        const progress = document.getElementById('progress');
        let objectUrl, submitting = false;
        const showError = message => { error.textContent = message; error.classList.remove('hidden'); };
        function selectImage() {
            error.classList.add('hidden');
            if (objectUrl) URL.revokeObjectURL(objectUrl);
            preview.classList.add('hidden');
            const file = input.files[0];
            document.getElementById('file-info').textContent = 'No image selected';
            if (!file) return;
            if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024) {
                input.value = '';
                showError('Choose a JPEG, PNG or WebP image up to 5 MB.');
                return;
            }
            document.getElementById('file-info').textContent = file.name + ' · ' + (file.size / 1024 / 1024).toFixed(2) + ' MB';
            objectUrl = URL.createObjectURL(file);
            preview.src = objectUrl;
            preview.classList.remove('hidden');
        }
        function updateCrop() {
            const selected = cropCatalogue[crop.value];
            const supported = Boolean(selected);
            input.disabled = !supported || submitting;
            button.disabled = !supported || submitting;
            document.getElementById('crop-help').textContent = selected ? selected.note : 'Choose a crop to review its available classes before uploading.';
            const list = document.getElementById('crop-classes');
            list.replaceChildren();
            (selected ? selected.classes : ['Choose a crop to see its classes.']).forEach(label => {
                const item = document.createElement('li');
                item.textContent = label.includes('___') ? label.split('___')[1].replaceAll('_', ' ') : label;
                list.appendChild(item);
            });
            dropzone.classList.toggle('opacity-50', !supported);
        }
        crop.addEventListener('change', () => {
            input.value = ''; selectImage(); updateCrop();
        });
        updateCrop();
        input.addEventListener('change', selectImage);
        preview.addEventListener('error', () => { input.value = ''; preview.classList.add('hidden'); showError('This image could not be opened. Please choose another file.'); });
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(event => dropzone.addEventListener(event, e => { e.preventDefault(); e.stopPropagation(); }));
        dropzone.addEventListener('dragover', () => dropzone.classList.add('ring-2', 'ring-emerald-600'));
        ['dragleave', 'drop'].forEach(event => dropzone.addEventListener(event, () => dropzone.classList.remove('ring-2', 'ring-emerald-600')));
        dropzone.addEventListener('drop', e => {
            if (submitting || input.disabled || !e.dataTransfer.files.length) return;
            const transfer = new DataTransfer();
            transfer.items.add(e.dataTransfer.files[0]);
            input.files = transfer.files;
            selectImage();
        });
        function resetForm() {
            submitting = false; crop.disabled = false; updateCrop();
            document.getElementById('spinner').classList.add('hidden');
            document.getElementById('button-label').textContent = 'Analyze leaf';
            form.removeAttribute('aria-busy'); progress.textContent = '';
        }
        window.addEventListener('pageshow', resetForm);
        form.addEventListener('submit', async e => {
            e.preventDefault();
            if (submitting || !form.reportValidity()) return;
            if (!Object.hasOwn(cropCatalogue, crop.value)) { updateCrop(); return; }
            submitting = true; button.disabled = true; input.disabled = true; crop.disabled = true;
            error.classList.add('hidden'); form.setAttribute('aria-busy', 'true');
            document.getElementById('spinner').classList.remove('hidden');
            document.getElementById('button-label').textContent = 'Preparing analysis…';
            try {
                const deadline = Date.now() + 180000;
                while (true) {
                    const response = await fetch(@json(route('detect.health')), {headers: {'Accept': 'application/json'}, signal: AbortSignal.timeout(15000)});
                    if (response.status === 401) throw new Error('Your session has expired. Please log in again before analyzing a leaf.');
                    if (!response.ok) throw new Error('The AI service is unavailable. Please try again shortly.');
                    const health = await response.json();
                    if (health.status === 'ready') break;
                    if (health.status !== 'loading') throw new Error('The AI model could not load. Please check the AI service logs or contact the administrator.');
                    if (Date.now() > deadline) throw new Error('The model is taking longer to initialize. Please try again in a few minutes.');
                    progress.textContent = 'Preparing the model. The first download may take a few minutes…';
                    await new Promise(resolve => setTimeout(resolve, 3000));
                }
                progress.textContent = 'Analyzing your leaf. Please keep this page open.';
                document.getElementById('button-label').textContent = 'Analyzing leaf…';
                input.disabled = false; crop.disabled = false;
                HTMLFormElement.prototype.submit.call(form);
            } catch (e) { resetForm(); showError(e.message || 'The AI service could not be reached. Please try again.'); }
        });
    </script>
</body>
</html>
