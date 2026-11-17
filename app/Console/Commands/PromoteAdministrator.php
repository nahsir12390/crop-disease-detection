<?php

namespace App\Console\Commands;

use App\Models\User;
use Illuminate\Console\Command;

class PromoteAdministrator extends Command
{
    protected $signature = 'app:make-admin {email : Email of an existing registered account}';

    protected $description = 'Grant administrator access to an existing active account';

    public function handle(): int
    {
        $user = User::where('email', mb_strtolower(trim($this->argument('email'))))->first();
        if (! $user || ! $user->is_active) {
            $this->error('Register an active account with this email first.');

            return self::FAILURE;
        }
        $user->is_admin = true;
        $user->save();
        $this->info('Administrator access granted to '.$user->email.'.');

        return self::SUCCESS;
    }
}
