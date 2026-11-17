<header class="border-b border-emerald-900/10 bg-white">
    <nav aria-label="Main navigation" class="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-5 px-5 py-5 sm:px-8">
        <a href="{{ route('home') }}" class="font-bold tracking-tight text-emerald-950">Crop Disease Detection<span class="block text-xs font-normal text-slate-500">Deep learning for leaf analysis</span></a>
        <div class="flex w-full flex-wrap items-center gap-x-5 gap-y-3 text-sm font-medium text-emerald-900 sm:w-auto">
            @foreach(['home' => 'Home', 'about' => 'About', 'contact' => 'Contact'] as $page => $label)
                <a href="{{ route($page) }}" @if(request()->routeIs($page)) aria-current="page" @endif class="rounded hover:underline focus-visible:outline-2 focus-visible:outline-emerald-700 {{ request()->routeIs($page) ? 'font-bold underline underline-offset-4' : '' }}">{{ $label }}</a>
            @endforeach
            @auth
                <a href="{{ route('detect') }}" class="hover:underline" @if(request()->routeIs('detect')) aria-current="page" @endif>My portal</a>
                @if(auth()->user()->is_admin ?? false)<a href="{{ url('/admin') }}" class="hover:underline">Admin</a>@endif
                <form method="POST" action="{{ route('logout') }}">@csrf<button type="submit" class="rounded-lg border border-emerald-800 px-4 py-2 hover:bg-emerald-50">Logout</button></form>
            @else
                <a href="{{ route('login') }}" class="hover:underline">Login</a>
                <a href="{{ route('register') }}" class="rounded-lg bg-emerald-900 px-4 py-2 text-white hover:bg-emerald-800">Create account</a>
            @endauth
        </div>
    </nav>
</header>
