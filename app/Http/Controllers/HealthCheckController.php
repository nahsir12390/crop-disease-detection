<?php

namespace App\Http\Controllers;

use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;

class HealthCheckController extends Controller
{
    public function __invoke()
    {
        try {
            DB::select('select 1');
            $response = Http::connectTimeout(1)->timeout(2)
                ->get(rtrim(config('services.crop_ai.url'), '/') . '/health');

            if (!$response->successful() || $response->json('status') !== 'ready' || $response->json('model_loaded') !== true) {
                return response()->json(['status' => 'unavailable'], 503);
            }

            return response()->json(['status' => 'ready']);
        } catch (\Throwable $exception) {
            return response()->json(['status' => 'unavailable'], 503);
        }
    }
}
