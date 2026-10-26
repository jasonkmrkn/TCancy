import Link from 'next/link';

const COLUMNS = [
    {
        title: 'Explore',
        links: [
            { href: '/vacancy', label: 'All vacancies' },
            { href: '/register', label: 'Create account' },
        ],
    },
    {
        title: 'Help',
        links: [
            { href: '/contact', label: 'Contact' },
            { href: '/login', label: 'Sign in' },
        ],
    },
];

export default function Footer() {
    return (
        <footer className="border-t border-zinc-200 bg-white">
            <div className="mx-auto grid w-full max-w-7xl gap-12 px-4 py-14 md:grid-cols-[2fr_1fr_1fr] md:px-6">
                <div>
                    <div className="flex items-baseline gap-0.5 text-xl font-semibold tracking-tighter text-zinc-900">
                        TCancy
                        <span aria-hidden className="h-1.5 w-1.5 rounded-[2px] bg-zinc-900" />
                    </div>
                    <p className="mt-4 max-w-[44ch] text-sm leading-relaxed text-zinc-500">
                        A job board posted by alumni for the students after them. Your NIK and ID card are visible only to the owner of a vacancy
                        you apply to.
                    </p>
                </div>

                {COLUMNS.map((col) => (
                    <nav key={col.title} aria-label={col.title}>
                        <h2 className="text-sm font-semibold text-zinc-900">{col.title}</h2>
                        <ul className="mt-4 flex flex-col gap-3">
                            {col.links.map((l) => (
                                <li key={l.href + l.label}>
                                    <Link href={l.href} className="text-sm text-zinc-500 transition-colors hover:text-zinc-900">
                                        {l.label}
                                    </Link>
                                </li>
                            ))}
                        </ul>
                    </nav>
                ))}
            </div>

            <div className="border-t border-zinc-200">
                <p className="mx-auto w-full max-w-7xl px-4 py-5 text-center text-xs text-zinc-500 md:px-6">
                    &copy; {new Date().getFullYear()} TCancy. Jobs and internships for HMTC ITS alumni.
                </p>
            </div>
        </footer>
    );
}