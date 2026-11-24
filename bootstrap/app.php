<?php

use Illuminate\Foundation\Application;
use Illuminate\Foundation\Configuration\Exceptions;
use Illuminate\Foundation\Configuration\Middleware;

return Application::configure(basePath: dirname(__DIR__))
    ->withRouting(
        web: __DIR__.'/../routes/web.php',
        commands: __DIR__.'/../routes/console.php',
        health: '/up',
        then: function () {
            // No session middleware: frequent health probes must not write SQLite sessions.
            \Illuminate\Support\Facades\Route::get('/healthz', \App\Http\Controllers\HealthCheckController::class);
        },
    )
    ->withMiddleware(function (Middleware $middleware): void {
        $middleware->redirectUsersTo('/portal');
        $middleware->alias(['active' => \App\Http\Middleware\EnsureActiveAccount::class, 'admin' => \App\Http\Middleware\EnsureAdmin::class]);
        $proxies = env('TRUSTED_PROXIES');
        if ($proxies) {
            $middleware->trustProxies(at: $proxies === '*' ? '*' : array_map('trim', explode(',', $proxies)));
        }
    })
    ->withExceptions(function (Exceptions $exceptions): void {
        //
    })->create();
