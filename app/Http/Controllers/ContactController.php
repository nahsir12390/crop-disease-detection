<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;

class ContactController extends Controller
{
    public function store(Request $request)
    {
        $data = $request->validate([
            'name' => ['required', 'string', 'max:100'],
            'email' => ['required', 'email', 'max:254'],
            'message' => ['required', 'string', 'min:10', 'max:3000'],
        ]);
        DB::table('contact_messages')->insert([...$data, 'created_at' => now(), 'updated_at' => now()]);

        return back()->with('status', 'Your message has been saved for the project administrator.');
    }
}
