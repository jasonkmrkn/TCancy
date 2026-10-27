'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { ArrowRight, ArrowUpRight, BriefcaseMetal } from '@phosphor-icons/react';
import Band, { SECTION_LABEL } from '@/components/home/Band';
import { api, ApiError } from '@/lib/api';
import { modeLabel, typeLabel } from '@/lib/labels';

type Job = {
    id: string;
    title: string;
    company: string;
    type: string;
    work_mode: string;
    location: string | null;
    deadline: string | null;
    skills: { id: string; name: string }[];
};

const EASE = 'ease-[cubic-bezier(0.16,1,0.3,1)]';

function RowSkeleton() {
    return (
        <li aria-hidden className="animate-pulse px-2 py-6">
            <div className="h-5 w-56 rounded-full bg-zinc-200/70" />
            <div className="mt-3 h-4 w-72 max-w-full rounded-full bg-zinc-200/70" />
            <div className="mt-4 flex gap-2">
                <div className="h-6 w-16 rounded-full bg-zinc-200/70" />
                <div className="h-6 w-20 rounded-full bg-zinc-200/70" />
            </div>
        </li>
    );
}

export default function LatestJobs() {
    const [jobs, setJobs] = useState<Job[] | null>(null);
    const [error, setError] = useState('');

    const load = useCallback(() => {
        setError('');
        setJobs(null);
        api<{ items: Job[] }>('/jobs', { query: { limit: 6 } })
            .then((r) => setJobs(r.items))
            .catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load vacancies.'));
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    return (
        <Band tone="base">
            <div className="grid gap-12 py-20 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-16">
                <div>
                    <p className={SECTION_LABEL}>Latest</p>
                    <h2 className="mt-3 max-w-[12ch] text-4xl font-semibold leading-[1.05] tracking-tighter text-zinc-900">
                        Newly opened vacancies
                    </h2>
                    <p className="mt-4 max-w-[38ch] leading-relaxed text-zinc-500">
                        Posted by alumni. Open one to read the role and its requirements.
                    </p>
                    <Link
                        href="/vacancy"
                        className={`group mt-8 inline-flex min-h-11 items-center gap-2 rounded-full px-4 text-sm font-medium text-zinc-900 transition-colors hover:bg-zinc-200/60 active:translate-y-[1px] active:scale-[0.98]`}
                    >
                        Filter vacancies
                        <ArrowRight
                            size={16}
                            weight="regular"
                            className={`transition-transform duration-300 ${EASE} group-hover:translate-x-0.5`}
                        />
                    </Link>
                </div>

                <div className="border-y border-zinc-200">
                    {error && (
                        <div role="alert" className="flex flex-col items-start gap-4 px-2 py-8">
                            <p className="text-sm text-red-700">{error}</p>
                            <button
                                onClick={load}
                                className="min-h-10 rounded-full border border-zinc-200 bg-white px-5 text-sm font-medium text-zinc-900 transition hover:border-zinc-300 active:translate-y-[1px] active:scale-[0.98]"
                            >
                                Try again
                            </button>
                        </div>
                    )}

                    {!error && jobs === null && (
                        <ul className="divide-y divide-zinc-200">
                            {[0, 1, 2, 3].map((i) => (
                                <RowSkeleton key={i} />
                            ))}
                        </ul>
                    )}

                    {jobs && jobs.length === 0 && (
                        <div className="flex flex-col items-start gap-3 px-2 py-10">
                            <span className="grid h-11 w-11 place-items-center rounded-full bg-zinc-100 text-zinc-600">
                                <BriefcaseMetal size={22} weight="regular" />
                            </span>
                            <p className="font-semibold tracking-tight text-zinc-900">No vacancies yet</p>
                            <p className="max-w-[40ch] text-sm leading-relaxed text-zinc-500">
                                No alumnus has posted a role yet. Alumni can register, get approved by an admin, and post the first one.
                            </p>
                            <Link href="/register" className="mt-1 text-sm font-medium text-zinc-900 underline-offset-4 hover:underline">
                                Create an account
                            </Link>
                        </div>
                    )}

                    {jobs && jobs.length > 0 && (
                        <ul className="divide-y divide-zinc-200">
                            {jobs.map((j, i) => (
                                <li key={j.id} className="rise" style={{ '--i': i } as React.CSSProperties}>
                                    <Link
                                        href={`/vacancy/${j.id}`}
                                        className={`group grid gap-4 px-2 py-6 transition-colors duration-300 hover:bg-white/70 sm:grid-cols-[1fr_auto] sm:items-center`}
                                    >
                                        <div className="min-w-0">
                                            <h3 className="text-lg font-semibold tracking-tight text-zinc-900">{j.title}</h3>
                                            <p className="mt-1 text-sm text-zinc-500">
                                                {j.company} · {typeLabel(j.type)} · {modeLabel(j.work_mode)}
                                                {j.location ? ` · ${j.location}` : ''}
                                            </p>
                                            {j.skills.length > 0 && (
                                                <div className="mt-3 flex flex-wrap gap-2">
                                                    {j.skills.slice(0, 4).map((s) => (
                                                        <span key={s.id} className="rounded-full bg-zinc-100 px-3 py-1 text-xs font-medium text-zinc-700">
                                                            {s.name}
                                                        </span>
                                                    ))}
                                                    {j.skills.length > 4 && (
                                                        <span className="px-1 py-1 font-mono text-xs text-zinc-500">+{j.skills.length - 4}</span>
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                        <div className="flex items-center gap-4 text-zinc-500">
                                            {j.deadline && <span className="font-mono text-xs">Apply by {j.deadline}</span>}
                                            <ArrowUpRight
                                                size={20}
                                                weight="regular"
                                                className={`transition-transform duration-300 ${EASE} group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-zinc-900`}
                                            />
                                        </div>
                                    </Link>
                                </li>
                            ))}
                        </ul>
                    )}
                </div>
            </div>
        </Band>
    );
}