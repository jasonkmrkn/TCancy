'use client';

import { usePathname } from 'next/navigation';

// Every page gets the standard centered container, except the home page,
// which lays out its own full-width bands (see components/home/Band.tsx).
export default function PageShell({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    if (pathname === '/') return <>{children}</>;
    return <div className="mx-auto w-full max-w-7xl px-4 py-8 md:px-6">{children}</div>;
}