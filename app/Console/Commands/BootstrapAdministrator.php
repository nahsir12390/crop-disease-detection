<?php

namespace App\Console\Commands;

use App\Models\User;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Validator;

class BootstrapAdministrator extends Command
{
    protected $signature = 'app:bootstrap-admin';

    protected $description = 'Provision the administrator configured in server environment variables';

    public function handle(): int
    {
        $email = config('admin.email');
        $password = config('admin.password');
        if (! $email && ! $password) {
            return self::SUCCESS;
        }
        $data = ['email' => mb_strtolower(trim((string) $email)), 'password' => $password, 'name' => config('admin.name')];
        $validator = Validator::make($data, ['email' => 'required|email|max:254', 'password' => 'required|string|min:12|max:128', 'name' => 'required|string|max:100']);
        if ($validator->fails()) {
            $this->error('Administrator configuration is invalid. Set ADMIN_EMAIL and ADMIN_PASSWORD (12 to 128 characters).');

            return self::FAILURE;
        }
        $user = User::firstOrNew(['email' => $data['email']]);
        $user->forceFill([...$data, 'is_admin' => true, 'is_active' => true])->save();
        $this->info('Configured administrator account provisioned.');

        return self::SUCCESS;
    }
}
