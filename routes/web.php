<?php

use App\Http\Controllers\DetectionController;
use Illuminate\Support\Facades\Route;

Route::get('/', [DetectionController::class, 'index'])->name('detect');
Route::post('/detect', [DetectionController::class, 'analyze'])->name('detect.analyze');
Route::get('/detect/health', [DetectionController::class, 'health'])->name('detect.health');
