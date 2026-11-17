<?php

use App\Http\Controllers\AccountController;
use App\Http\Controllers\AdminController;
use App\Http\Controllers\ContactController;
use App\Http\Controllers\DetectionController;
use Illuminate\Support\Facades\Route;

Route::view('/', 'pages.home')->name('home');
Route::view('/about', 'pages.about')->name('about');
Route::view('/contact', 'pages.contact')->name('contact');
Route::post('/contact', [ContactController::class, 'store'])->middleware('throttle:5,1')->name('contact.store');

Route::middleware('guest')->group(function () {
    Route::view('/login', 'account.form', ['register' => false])->name('login');
    Route::view('/register', 'account.form', ['register' => true])->name('register');
    Route::post('/login', [AccountController::class, 'login'])->middleware('throttle:6,1');
    Route::post('/register', [AccountController::class, 'register'])->middleware('throttle:5,1');
});
Route::middleware(['auth', 'active'])->group(function () {
    Route::get('/portal', [DetectionController::class, 'index'])->name('detect');
    Route::post('/detect', [DetectionController::class, 'analyze'])->name('detect.analyze');
    Route::get('/detect/health', [DetectionController::class, 'health'])->name('detect.health');
    Route::post('/logout', [AccountController::class, 'logout'])->name('logout');
    Route::middleware('admin')->prefix('admin')->name('admin.')->group(function () {
        Route::get('/', [AdminController::class, 'index'])->name('index');
        Route::patch('/users/{user}/status', [AdminController::class, 'status'])->name('users.status');
        Route::patch('/messages/{message}/read', [AdminController::class, 'read'])->whereNumber('message')->name('messages.read');
    });
});
