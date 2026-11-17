<?php

namespace Tests\Feature;

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Hash;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class AccountAccessTest extends TestCase
{
    use RefreshDatabase;

    public function test_public_pages_and_all_portal_routes_are_protected(): void
    {
        foreach (['/', '/about', '/contact', '/login', '/register'] as $path) {
            $this->get($path)->assertOk();
        }
        Http::fake();
        $this->get('/portal')->assertRedirect('/login');
        $this->post('/detect')->assertRedirect('/login');
        $this->getJson('/detect/health')->assertUnauthorized();
        $this->get('/admin')->assertRedirect('/login');
        Http::assertNothingSent();
    }

    public function test_registration_hashes_password_and_cannot_grant_admin(): void
    {
        $this->post('/register', ['name' => 'Grower', 'email' => 'GROWER@example.test', 'password' => 'strong-password', 'password_confirmation' => 'strong-password', 'is_admin' => true])
            ->assertRedirect('/portal');
        $user = User::firstOrFail();
        $this->assertAuthenticatedAs($user);
        $this->assertTrue(Hash::check('strong-password', $user->password));
        $this->assertFalse($user->is_admin);
        $this->assertSame('grower@example.test', $user->email);
        $this->get('/portal')->assertOk()->assertSee('Logout');
        $this->get('/admin')->assertForbidden();
    }

    public function test_bad_credentials_and_suspended_accounts_cannot_login(): void
    {
        $user = User::factory()->create();
        $this->post('/login', ['email' => $user->email, 'password' => 'wrong'])->assertSessionHasErrors('email');
        $this->assertGuest();
        $user->forceFill(['is_active' => false])->save();
        $this->post('/login', ['email' => $user->email, 'password' => 'password'])->assertSessionHasErrors('email');
        $this->assertGuest();
    }

    public function test_login_restores_intended_portal_and_logout_removes_access(): void
    {
        $user = User::factory()->create();
        $this->get('/portal')->assertRedirect('/login');
        $this->post('/login', ['email' => $user->email, 'password' => 'password'])->assertRedirect('/portal');
        $this->assertAuthenticatedAs($user);
        $this->withSession(['prediction' => ['private' => 'old']])->post('/logout')->assertRedirect('/')->assertSessionMissing('prediction');
        $this->assertGuest();
        $this->get('/portal')->assertRedirect('/login');
        $this->get('/logout')->assertMethodNotAllowed();
    }

    public function test_registration_validates_confirmation_and_duplicate_email(): void
    {
        $user = User::factory()->create();
        $this->post('/register', ['name' => 'Test', 'email' => $user->email, 'password' => 'short', 'password_confirmation' => 'different'])->assertSessionHasErrors(['email', 'password']);
        $this->assertSame(1, User::count());
    }

    public function test_login_is_rate_limited(): void
    {
        for ($attempt = 0; $attempt < 6; $attempt++) {
            $this->post('/login', ['email' => 'absent@example.test', 'password' => 'incorrect'])->assertSessionHasErrors();
        }
        $this->post('/login', ['email' => 'absent@example.test', 'password' => 'incorrect'])->assertStatus(429);
    }

    public function test_admin_can_suspend_users_and_existing_sessions_are_blocked(): void
    {
        $admin = User::factory()->create(['is_admin' => true]);
        $user = User::factory()->create();
        $this->actingAs($user)->patch('/admin/users/'.$admin->id.'/status', ['is_active' => false])->assertForbidden();
        $this->actingAs($admin)->patch('/admin/users/'.$user->id.'/status', ['is_active' => false])->assertRedirect('/admin');
        $this->assertFalse($user->fresh()->is_active);
        $this->actingAs($user->fresh())->get('/portal')->assertRedirect('/login');
        $this->assertGuest();
        $this->actingAs($admin)->patch('/admin/users/'.$admin->id.'/status', ['is_active' => false])->assertForbidden();
        $this->actingAs($admin)->patch('/admin/users/'.$user->id.'/status', ['is_active' => true])->assertRedirect('/admin');
        $this->assertTrue($user->fresh()->is_active);
    }

    public function test_contact_messages_are_private_and_escaped_in_admin_inbox(): void
    {
        $this->from('/contact')->post('/contact', ['name' => 'Visitor', 'email' => 'visitor@example.test', 'message' => '<script>alert(1)</script>'])->assertRedirect('/contact')->assertSessionHas('status');
        $id = DB::table('contact_messages')->value('id');
        $this->actingAs(User::factory()->create())->get('/admin')->assertForbidden();
        $this->patch('/admin/messages/'.$id.'/read')->assertForbidden();
        $admin = User::factory()->create(['is_admin' => true]);
        $this->actingAs($admin)->get('/admin')->assertOk()->assertSee('&lt;script&gt;', false)->assertDontSee('<script>alert(1)</script>', false);
        $this->patch('/admin/messages/'.$id.'/read')->assertRedirect('/admin');
        $this->assertNotNull(DB::table('contact_messages')->where('id', $id)->value('read_at'));
    }

    public function test_bootstrap_admin_requires_valid_server_configuration(): void
    {
        config(['admin.email' => 'owner@example.test', 'admin.password' => 'long-owner-password', 'admin.name' => 'Owner']);
        $this->artisan('app:bootstrap-admin')->assertSuccessful();
        $admin = User::where('email', 'owner@example.test')->firstOrFail();
        $this->assertTrue($admin->is_admin);
        $this->assertTrue(Hash::check('long-owner-password', $admin->password));
        $this->artisan('app:bootstrap-admin')->assertSuccessful();
        $this->assertSame(1, User::count());
        config(['admin.password' => 'short']);
        $this->artisan('app:bootstrap-admin')->assertFailed();
    }

    public function test_admin_password_provisioning_revokes_previous_account_sessions(): void
    {
        $user = User::factory()->create();
        $this->post('/login', ['email' => $user->email, 'password' => 'password'])->assertRedirect('/portal');
        config(['admin.email' => $user->email, 'admin.password' => 'new-owner-secret-password']);
        $this->artisan('app:bootstrap-admin')->assertSuccessful();
        $this->actingAs($user->fresh())->get('/admin')->assertRedirect('/login');
        $this->assertGuest();
    }
}
