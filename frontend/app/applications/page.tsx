'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowClockwise, ArrowUpRight, MapPin } from '@phosphor-icons/react';
import { stagger } from '@/components/AuthShell';
import Chip from '@/components/Chip';
import { FormAlert } from '@/components/FormField';
import type { Job } from '@/components/JobCard';
import { BTN_OUTLINE, BTN_PRIMARY, EASE, PageHeader, Pill, SignInNotice } from '@/components/ui';
import { api, ApiError } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { modeLabel, typeLabel } from '@/lib/labels';

type Item = { id: string; status: string; created_at: string; job: Job };

const STATUS_LABEL: Record<string, string> = {
  submitted: 'Submitted',
  shortlisted: 'Shortlisted',
  accepted: 'Accepted',
  rejected: 'Rejected',
  withdrawn: 'Withdrawn',
};

function StatusBadge({ status }: { status: string }) {
  const tone = status === 'accepted' ? 'solid' : status === 'rejected' || status === 'withdrawn' ? 'muted' : 'outline';
  return <Pill tone={tone}>{STATUS_LABEL[status] ?? status}</Pill>;
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

function ListSkeleton() {
  return (
    <ul aria-hidden className="mt-8 animate-pulse divide-y divide-zinc-200 border-y border-zinc-200">
      {[0, 1, 2, 3].map((i) => (
        <li key={i} className="flex items-center justify-between gap-6 px-2 py-6">
          <div className="flex flex-col gap-3">
            <div className="h-5 w-64 max-w-full rounded-full bg-zinc-200/70" />
            <div className="h-4 w-40 rounded-full bg-zinc-200/70" />
          </div>
          <div className="h-4 w-24 rounded-full bg-zinc-200/70" />
        </li>
      ))}
    </ul>
  );
}

export default function ApplicationsPage() {
  const { user, loading } = useAuth();
  const [items, setItems] = useState<Item[] | null>(null);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('all');
  const allowed = user?.role === 'applicant' && user.status === 'active';

  const load = useCallback(() => {
    setError('');
    api<Item[]>('/me/applications')
      .then(setItems)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load applications.'));
  }, []);

  useEffect(() => {
    if (allowed) load();
  }, [allowed, load]);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const a of items ?? []) c[a.status] = (c[a.status] ?? 0) + 1;
    return c;
  }, [items]);

  if (loading) {
    return (
      <div className="py-4">
        <div aria-hidden className="flex animate-pulse flex-col gap-5">
          <div className="h-4 w-24 rounded-full bg-zinc-200/70" />
          <div className="h-12 w-80 max-w-full rounded-full bg-zinc-200/70" />
        </div>
        <ListSkeleton />
      </div>
    );
  }

  if (!allowed) {
    return (
      <SignInNotice title="My applications">
        Only active applicants have applications.{' '}
        {!user && (
          <Link href="/login" className="font-medium text-zinc-900 underline underline-offset-4">
            Sign in
          </Link>
        )}
      </SignInNotice>
    );
  }

  const present = Object.keys(STATUS_LABEL).filter((s) => counts[s]);
  const visible = (items ?? []).filter((a) => filter === 'all' || a.status === filter);

  return (
    <div className="py-4">
      <PageHeader
        eyebrow="Account"
        title="My applications"
        subtitle="Every vacancy you applied to, and where each one stands."
        action={
          <Link href="/vacancy" className={BTN_OUTLINE}>
            Browse vacancies
          </Link>
        }
      />

      {error && (
        <div className="mt-10 flex flex-col items-start gap-3">
          <FormAlert>{error}</FormAlert>
          <button type="button" onClick={load} className={BTN_OUTLINE}>
            <ArrowClockwise size={16} />
            Try again
          </button>
        </div>
      )}

      {!items && !error && <ListSkeleton />}

      {items && items.length === 0 && (
        <div className="rise mt-10 flex flex-col items-start gap-4 rounded-[2rem] border border-dashed border-zinc-300 px-8 py-12" style={stagger(1)}>
          <p className="max-w-[44ch] text-zinc-500">You have not applied to anything yet. Find a vacancy posted by an alumnus and apply.</p>
          <Link href="/vacancy" className={BTN_PRIMARY}>
            Browse vacancies
          </Link>
        </div>
      )}

      {items && items.length > 0 && (
        <>
          <div className="rise mt-10 flex flex-wrap gap-2" role="group" aria-label="Filter by status" style={stagger(1)}>
            <Chip selected={filter === 'all'} onClick={() => setFilter('all')}>
              All <span className="ml-1 font-mono text-xs opacity-70">{items.length}</span>
            </Chip>
            {present.map((s) => (
              <Chip key={s} selected={filter === s} onClick={() => setFilter(filter === s ? 'all' : s)}>
                {STATUS_LABEL[s]} <span className="ml-1 font-mono text-xs opacity-70">{counts[s]}</span>
              </Chip>
            ))}
          </div>

          <ul className="rise mt-6 divide-y divide-zinc-200 border-y border-zinc-200" style={stagger(2)}>
            {visible.map((a) => (
              <li key={a.id}>
                <Link
                  href={`/applications/${a.id}`}
                  className={`group grid gap-4 px-2 py-6 transition-colors duration-300 hover:bg-white/70 sm:grid-cols-[1fr_auto] sm:items-center`}
                >
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-center gap-3 text-xl font-semibold tracking-tight text-zinc-900">
                      {a.job.title}
                      <StatusBadge status={a.status} />
                      {a.job.status === 'closed' && <Pill tone="muted">Vacancy closed</Pill>}
                    </p>
                    <p className="mt-1.5 text-sm text-zinc-500">
                      {a.job.company}
                      <span aria-hidden> · </span>
                      {typeLabel(a.job.type)}
                      <span aria-hidden> · </span>
                      {modeLabel(a.job.work_mode)}
                      {a.job.location && (
                        <span className="ml-3 inline-flex items-center gap-1">
                          <MapPin size={14} />
                          {a.job.location}
                        </span>
                      )}
                    </p>
                  </div>
                  <div className="flex items-center gap-4 text-zinc-500">
                    <span className="font-mono text-xs">Applied {formatDate(a.created_at)}</span>
                    <ArrowUpRight
                      size={20}
                      className={`transition-transform duration-300 ${EASE} group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-zinc-900`}
                    />
                  </div>
                </Link>
              </li>
            ))}
            {visible.length === 0 && (
              <li className="px-2 py-10 text-zinc-500">No applications with this status.</li>
            )}
          </ul>
        </>
      )}
    </div>
  );
}