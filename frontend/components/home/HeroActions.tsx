'use client';

import Link from 'next/link';
import { ArrowRight } from '@phosphor-icons/react';
import { useAuth } from '@/lib/auth';

export default function HeroActions() {
    const { user, loading } = useAuth();

    return (
        <div className="mt-10 flex flex-wrap items-center gap-3">
            <Link
                href="/vacancy"
                className="group inline-flex min-h-12 items-center gap-2 rounded-full bg-zinc-900 px-6 text-sm font-medium text-zinc-50 shadow-[inset_0_1px_0_rgba(255,255,255,0.12)] transition duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] hover:bg-zinc-800 active:translate-y-[1px] active:scale-[0.98] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900"
            >
                Browse vacancies
                <ArrowRight
                    size={16}
                    weight="regular"
                    className="transition-transform duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] group-hover:translate-x-0.5"
                />
            </Link>
            {!loading && !user && (
                <Link
                    href="/register"
                    className="inline-flex min-h-12 items-center rounded-full px-5 text-sm font-medium text-zinc-900 transition-colors hover:bg-zinc-200/60 active:translate-y-[1px] active:scale-[0.98]"
                >
                    Create account
                </Link>
            )}
        </div>
    );
}