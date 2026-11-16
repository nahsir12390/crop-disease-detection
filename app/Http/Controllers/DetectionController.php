<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use Illuminate\Support\Facades\Http;
use Illuminate\View\View;

class DetectionController extends Controller
{
    public function index(): View
    {
        return view('detect');
    }

    public function analyze(Request $request)
    {
        $validated = $request->validate([
            'image' => ['required', 'image', 'mimes:jpg,jpeg,png,webp', 'max:5120'],
        ]);

        $url = rtrim(config('services.crop_ai.url', 'http://127.0.0.1:8001'), '/');

        try {
            $response = Http::timeout(30)
                ->attach('file', file_get_contents($validated['image']->getRealPath()), $validated['image']->getClientOriginalName())
                ->post($url . '/predict');

            if ($response->status() === 503) {
                return back()->with('notice', 'AI model is not trained or loaded yet. Image validation succeeded.');
            }

            if (!$response->successful()) {
                return back()->withErrors(['image' => 'The analysis service could not process this image. Please try again.']);
            }

            return back()->with('prediction', $response->json());
        } catch (\Illuminate\Http\Client\ConnectionException $e) {
            return back()->withErrors(['image' => 'AI service is offline. Start FastAPI on port 8001.']);
        }
    }
}
