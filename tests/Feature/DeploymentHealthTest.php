<?php

namespace Tests\Feature;

use App\Providers\AppServiceProvider;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class DeploymentHealthTest extends TestCase
{
    public function test_readiness_checks_sqlite_and_model_without_creating_a_session(): void
    {
        Http::fake(['*/health' => Http::response(['status' => 'ready', 'model_loaded' => true])]);
        $this->getJson('/healthz')->assertOk()->assertExactJson(['status' => 'ready'])->assertHeaderMissing('Set-Cookie');
        Http::assertSentCount(1);
    }

    public function test_loading_model_is_not_ready(): void
    {
        Http::fake(['*/health' => Http::response(['status' => 'loading', 'model_loaded' => false])]);
        $this->getJson('/healthz')->assertStatus(503)->assertExactJson(['status' => 'unavailable']);
    }

    public function test_unreachable_ai_is_not_ready(): void
    {
        Http::fake(fn () => throw new ConnectionException('Internal address must not be exposed'));
        $this->getJson('/healthz')->assertStatus(503)->assertExactJson(['status' => 'unavailable']);
    }

    public function test_database_failure_is_not_ready_and_details_are_private(): void
    {
        DB::shouldReceive('select')->once()->andThrow(new \PDOException('Private database path'));
        $this->getJson('/healthz')->assertStatus(503)->assertExactJson(['status' => 'unavailable']);
    }

    public function test_render_https_setting_generates_https_form_and_health_urls(): void
    {
        config(['app.force_https' => true]);
        (new AppServiceProvider($this->app))->boot();
        $this->get('/')->assertOk()->assertSee('https://localhost/register', false);
    }
}
