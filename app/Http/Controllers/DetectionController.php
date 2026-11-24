<?php

namespace App\Http\Controllers;

use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Validator;
use Illuminate\Validation\Rule;
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
            'crop' => ['required', Rule::in(array_keys(config('crops')))],
            'image' => ['required', 'image', 'mimes:jpg,jpeg,png,webp', 'max:5120'],
        ]);

        $url = rtrim(config('services.crop_ai.url', 'http://127.0.0.1:8001'), '/');

        try {
            $response = Http::connectTimeout(config('services.crop_ai.connect_timeout'))
                ->timeout(config('services.crop_ai.timeout'))
                ->attach('file', file_get_contents($validated['image']->getRealPath()), $validated['image']->getClientOriginalName())
                ->post($url.'/predict', ['crop' => $validated['crop']]);

            if ($response->status() === 503) {
                return back()->withInput($request->only('crop'))->withErrors(['image' => 'The AI model is still initializing or could not load. Please wait a moment and try again. If this continues, check the AI service logs.']);
            }

            if (! $response->successful()) {
                Log::warning('Crop AI request failed', ['status' => $response->status()]);
                if (in_array($response->status(), [413, 422])) {
                    return back()->withInput($request->only('crop'))->withErrors(['image' => 'Please upload a valid, still JPEG, PNG or WebP image, up to 5 MB and 20 megapixels.']);
                }

                return back()->withInput($request->only('crop'))->withErrors(['image' => 'The analysis service could not process this image. Please try again.']);
            }

            $prediction = $response->json();
            $rules = ['label' => 'required|string', 'crop' => 'required|string', 'disease' => 'required|string',
                'confidence' => 'required|numeric|between:0,1', 'uncertain' => 'required|boolean',
                'selected_crop' => 'required|in:'.$validated['crop'],
                'top_predictions' => 'required|array|min:1|max:3', 'top_predictions.*.display_label' => 'required|string',
                'top_predictions.*.label' => 'required|string',
                'top_predictions.*.confidence' => 'required|numeric|between:0,1'];
            if (! is_array($prediction) || Validator::make($prediction, $rules)->fails()) {
                Log::error('Crop AI returned an invalid prediction response');

                return back()->withInput($request->only('crop'))->withErrors(['image' => 'The analysis service returned an incomplete result. Please try again.']);
            }
            $catalogue = config('crops')[$validated['crop']];
            $prefix = $catalogue['prefix'];
            foreach ([$prediction, ...$prediction['top_predictions']] as $match) {
                if (! str_starts_with($match['label'], $prefix) || ! in_array($match['label'], $catalogue['classes'], true)) {
                    Log::error('Crop AI returned a class outside the selected crop');

                    return back()->withInput($request->only('crop'))->withErrors(['image' => 'The analysis service returned a result for another crop. Please try again.']);
                }
            }
            $prediction['limited_coverage'] = $catalogue['coverage'] !== 'healthy_and_diseases';
            $prediction['coverage_note'] = $catalogue['note'];
            if ($prediction['limited_coverage']) {
                $prediction['uncertain'] = true;
                $prediction['uncertainty_reason'] = 'limited_coverage';
            }

            return back()->withInput($request->only('crop'))->with('prediction', $prediction);
        } catch (ConnectionException $e) {
            Log::warning('Crop AI connection failed', ['exception' => $e->getMessage()]);

            return back()->withInput($request->only('crop'))->withErrors(['image' => 'The AI service could not be reached or took too long to respond. Please try again shortly.']);
        }
    }

    public function health()
    {
        try {
            $response = Http::connectTimeout(config('services.crop_ai.connect_timeout'))->timeout(10)
                ->get(rtrim(config('services.crop_ai.url'), '/').'/health');
            $status = $response->json('status');
            if (! $response->successful() || ! in_array($status, ['loading', 'ready', 'error'])) {
                return response()->json(['status' => 'offline'], 503);
            }

            return response()->json(['status' => $status]);
        } catch (ConnectionException $e) {
            return response()->json(['status' => 'offline'], 503);
        }
    }
}
