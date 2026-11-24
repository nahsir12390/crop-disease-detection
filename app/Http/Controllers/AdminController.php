<?php

namespace App\Http\Controllers;

use App\Models\User;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;

class AdminController extends Controller
{
    public function index()
    {
        return view('admin.index', [
            'users' => User::latest('id')->paginate(10, ['*'], 'users_page')->withQueryString(),
            'messages' => DB::table('contact_messages')->latest('id')->paginate(10, ['*'], 'messages_page')->withQueryString(),
            'userCount' => User::count(),
            'unreadCount' => DB::table('contact_messages')->whereNull('read_at')->count(),
        ]);
    }

    public function status(Request $request, User $user)
    {
        abort_if($user->is_admin || $user->is($request->user()), 403, 'Administrator accounts cannot be suspended here.');
        $data = $request->validate(['is_active' => ['required', 'boolean']]);
        $user->is_active = (bool) $data['is_active'];
        $user->save();

        return redirect()->route('admin.index')->with('status', 'Account status updated.');
    }

    public function read(string $message)
    {
        abort_unless(DB::table('contact_messages')->where('id', $message)->exists(), 404);
        DB::table('contact_messages')->where('id', $message)->whereNull('read_at')->update(['read_at' => now(), 'updated_at' => now()]);

        return redirect()->route('admin.index')->with('status', 'Message marked as read.');
    }
}
