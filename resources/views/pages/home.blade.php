@extends('layouts.site')
@section('title', 'Home | Crop Disease Detection')
@section('content')
<section class="grid items-center gap-10 lg:grid-cols-2">
    <div><p class="text-xs font-bold uppercase tracking-widest text-emerald-700">Crop health, a closer look</p><h1 class="mt-5 text-4xl font-semibold leading-tight tracking-tight text-emerald-950 sm:text-6xl">Understand what your leaves may be telling you.</h1><p class="mt-6 text-lg leading-8 text-slate-600">Explore possible leaf diseases in Tomato, Maize and bell Pepper with image classification. Create your account to access the leaf analysis portal.</p><a href="{{ auth()->check() ? route('detect') : route('register') }}" class="mt-8 inline-block rounded-xl bg-emerald-900 px-6 py-4 font-semibold text-white hover:bg-emerald-800">{{ auth()->check() ? 'Open my portal' : 'Get started' }}</a></div>
    <div class="rounded-3xl bg-emerald-950 p-8 text-white sm:p-12"><h2 class="text-2xl font-semibold">From a photograph to possible matches</h2><ol class="mt-7 space-y-6 text-emerald-100"><li><strong class="text-white">01. Create an account</strong><p class="mt-1">Register and sign in to the portal.</p></li><li><strong class="text-white">02. Choose a crop and photo</strong><p class="mt-1">Upload a clear JPEG, PNG or WebP leaf photo up to 5 MB.</p></li><li><strong class="text-white">03. Explore the result</strong><p class="mt-1">Review possible classes, model scores and uncertainty notices.</p></li></ol></div>
</section>
<p class="mt-12 max-w-3xl text-sm leading-7 text-slate-500">Predictions are preliminary, and field photographs can be misclassified. Cassava and other unsupported crops cannot be analyzed by the current system.</p>
@endsection
