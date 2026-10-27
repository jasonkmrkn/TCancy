'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowClockwise, ArrowUpRight, MapPin, PencilSimple, Plus, UsersThree } from '@phosphor-icons/react';
import { stagger } from '@/components/AuthShell';
import Chip from '@/components/Chip';
import { FormAlert } from '@/components/FormField';
import type { Job } from '@/components/JobCard';
import { NotAllowed, useIsOwnerRole } from '@/components/OwnerGate';
import { BTN_OUTLINE, BTN_PRIMARY, EASE, PageHeader, Pill } from '@/components/ui';
import { api, ApiError } from '@/lib/api';
import { modeLabel, typeLabel } from '@/lib/labels';

type Filter = 'all' | 'open' | 'closed';

function daysLeft(deadline: string): number {
  const end = new Date(deadline + 'T23:59:59');
  return Math.ceil((end.getTime() - Date.now()) / 86_400_000);
}

function formatDate(value: string): string {
  const d = new Date(value.length === 10 ? value + 'T00:00:00' : value);
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

function Deadline({ deadline, closed }: { deadline: string; closed: boolean }) {
  const left = daysLeft(deadline);
  let note = '';
  if (!closed) note = left < 0 ? 'passed' : left === 0 ? 'today' : left === 1 ? '1 day left' : `${left} days left`;
  return (
    <span className="font-mono text-xs text-zinc-500">
      Deadline {formatDate(deadline)}
      {note && <span className={left <= 3 ? ' font-semibold text-zinc-900' : ''}> · {note}</span>}
    </span>
  );
}

function ListSkeleton() {
  return (
    <ul aria-hidden className="mt-8 animate-pulse divide-y divide-zinc-200 border-y border-zinc-200">
      {[0, 1, 2].map((i) => (
        <li key={i} className="flex flex-col gap-4 px-2 py-7">
          <div className="h-6 w-72 max-w-full rounded-full bg-zinc-200/70" />
          <div className="h-4 w-56 rounded-full bg-zinc-200/70" />
          <div className="mt-2 flex gap-3">
            <div className="h-10 w-28 rounded-full bg-zinc-200/70" />
            <div className="h-10 w-20 rounded-full bg-zinc-200/70" />
          </div>
        </li>
      ))}
    </ul>
  );
}

const ACTION =
  `inline-flex min-h-10 items-center gap-1.5 rounded-full border px-4 text-sm font-medium transition duration-300 ${EASE} active:scale-[0.98] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900`;

export default function MyJobsPage() {
  const { loading, allowed } = useIsOwnerRole();
  const [items, setItems] = useState<Job[] | null>(null);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState<Filter>('all');
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState('');

  const load = useCallback(() => {
    setError('');
    api<Job[]>('/me/jobs')
      .then(setItems)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load vacancies.'));
  }, []);

  useEffect(() => {
    if (allowed) load();
  }, [allowed, load]);

  async function close(job: Job) {
    setBusyId(job.id);
    setError('');
    try {
      await api(`/jobs/${job.id}/close`, { method: 'POST' });
      setItems((list) => (list ?? []).map((j) => (j.id === job.id ? { ...j, status: 'closed' } : j)));
      setConfirmId(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not close the vacancy.');
    } finally {
      setBusyId('');
    }
  }

  const counts = useMemo(() => {
    const list = items ?? [];
    return { all: list.length, open: list.filter((j) => j.status === 'open').length, closed: list.filter((j) => j.status === 'closed').length };
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
  if (!allowed) return <NotAllowed />;

  const visible = (items ?? []).filter((j) => filter === 'all' || j.status === filter);

  return (
    <div className="py-4">
      <PageHeader
        eyebrow="Vacancies"
        title="My vacancies"
        subtitle="Vacancies you posted for the students after you. Open the applicants to review and decide."
        action={
          <Link href="/jobs/new" className={BTN_PRIMARY}>
            <Plus size={16} weight="bold" />
            New vacancy
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
        <div
          className="rise mt-10 flex flex-col items-start gap-4 rounded-[2rem] border border-dashed border-zinc-300 px-8 py-12"
          style={stagger(1)}
        >
          <p className="max-w-[46ch] text-zinc-500">
            You have not posted any vacancies yet. Post one and applicants from HMTC ITS can start applying.
          </p>
          <Link href="/jobs/new" className={BTN_PRIMARY}>
            <Plus size={16} weight="bold" />
            Post your first vacancy
          </Link>
        </div>
      )}

      {items && items.length > 0 && (
        <>
          <div className="rise mt-10 flex flex-wrap gap-2" role="group" aria-label="Filter by status" style={stagger(1)}>
            {(['all', 'open', 'closed'] as Filter[]).map((f) => (
              <Chip key={f} selected={filter === f} onClick={() => setFilter(f)}>
                {f === 'all' ? 'All' : f === 'open' ? 'Open' : 'Closed'}
                <span className="ml-1 font-mono text-xs opacity-70">{counts[f]}</span>
              </Chip>
            ))}
          </div>

          <ul className="rise mt-6 divide-y divide-zinc-200 border-y border-zinc-200" style={stagger(2)}>
            {visible.map((job) => {
              const closed = job.status === 'closed';
              return (
                <li key={job.id} className="px-2 py-7">
                  <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
                    <div className="min-w-0">
                      <p className="flex flex-wrap items-center gap-3 text-xl font-semibold tracking-tight text-zinc-900">
                        <Link
                          href={`/vacancy/${job.id}`}
                          className="group inline-flex items-center gap-1.5 underline-offset-4 hover:underline"
                        >
                          {job.title}
                          <ArrowUpRight
                            size={16}
                            className={`text-zinc-400 transition-transform duration-300 ${EASE} group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-zinc-900`}
                          />
                        </Link>
                        <Pill tone={closed ? 'muted' : 'solid'}>{closed ? 'Closed' : 'Open'}</Pill>
                      </p>
                      <p className="mt-1.5 text-sm text-zinc-500">
                        {job.company}
                        <span aria-hidden> · </span>
                        {typeLabel(job.type)}
                        <span aria-hidden> · </span>
                        {modeLabel(job.work_mode)}
                        {job.location && (
                          <span className="ml-3 inline-flex items-center gap-1">
                            <MapPin size={14} />
                            {job.location}
                          </span>
                        )}
                      </p>
                    </div>
                    {job.deadline && <Deadline deadline={job.deadline} closed={closed} />}
                  </div>

                  {job.skills.length > 0 && (
                    <ul className="mt-4 flex flex-wrap gap-2" aria-label="Required skills">
                      {job.skills.map((s) => (
                        <li key={s.id} className="rounded-full bg-zinc-100 px-3 py-1 text-xs text-zinc-700">
                          {s.name}
                        </li>
                      ))}
                    </ul>
                  )}

                  <div className="mt-5 flex flex-wrap items-center gap-2">
                    {confirmId === job.id ? (
                      <>
                        <span className="mr-1 text-sm text-zinc-600">Close this vacancy? Applicants can no longer apply.</span>
                        <button
                          type="button"
                          disabled={busyId === job.id}
                          onClick={() => close(job)}
                          className={`${ACTION} border-zinc-900 bg-zinc-900 text-zinc-50 hover:bg-zinc-800 disabled:opacity-50`}
                        >
                          {busyId === job.id ? 'Closing...' : 'Yes, close it'}
                        </button>
                        <button
                          type="button"
                          onClick={() => setConfirmId(null)}
                          className={`${ACTION} border-zinc-200 bg-white text-zinc-700 hover:border-zinc-400`}
                        >
                          Cancel
                        </button>
                      </>
                    ) : (
                      <>
                        <Link
                          href={`/jobs/${job.id}/applicants`}
                          className={`${ACTION} border-zinc-900 bg-zinc-900 text-zinc-50 hover:bg-zinc-800`}
                        >
                          <UsersThree size={16} />
                          Applicants
                        </Link>
                        {!closed && (
                          <>
                            <Link
                              href={`/jobs/${job.id}/edit`}
                              className={`${ACTION} border-zinc-200 bg-white text-zinc-900 hover:border-zinc-400`}
                            >
                              <PencilSimple size={16} />
                              Edit
                            </Link>
                            <button
                              type="button"
                              onClick={() => setConfirmId(job.id)}
                              className={`${ACTION} border-transparent text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900`}
                            >
                              Close
                            </button>
                          </>
                        )}
                      </>
                    )}
                  </div>
                </li>
              );
            })}
            {visible.length === 0 && <li className="px-2 py-10 text-zinc-500">No {filter} vacancies.</li>}
          </ul>
        </>
      )}
    </div>
  );
}