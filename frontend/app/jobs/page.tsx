'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import type { Job } from '@/components/JobCard';
import { NotAllowed, useIsOwnerRole } from '@/components/OwnerGate';
import { api, ApiError } from '@/lib/api';

export default function MyJobsPage() {
  const { loading, allowed } = useIsOwnerRole();
  const [items, setItems] = useState<Job[] | null>(null);
  const [error, setError] = useState('');
  const [busyId, setBusyId] = useState('');

  useEffect(() => {
    if (!allowed) return;
    api<Job[]>('/me/jobs')
      .then(setItems)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load vacancies.'));
  }, [allowed]);

  async function close(job: Job) {
    if (!window.confirm(`Close "${job.title}"? Applicants will no longer be able to apply.`)) return;
    setBusyId(job.id);
    setError('');
    try {
      await api(`/jobs/${job.id}/close`, { method: 'POST' });
      setItems((list) => (list ?? []).map((j) => (j.id === job.id ? { ...j, status: 'closed' } : j)));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not close the vacancy.');
    } finally {
      setBusyId('');
    }
  }

  if (loading) return <p className="text-sm text-gray-600">Loading...</p>;
  if (!allowed) return <NotAllowed />;

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">My vacancies</h1>
        <Link href="/jobs/new" className="rounded border px-3 py-1 text-sm">
          New vacancy
        </Link>
      </div>
      {error && <p className="mt-3 text-sm text-red-700">{error}</p>}
      {!items && !error && <p className="mt-3 text-sm text-gray-600">Loading...</p>}
      {items && items.length === 0 && <p className="mt-3 text-sm">You have not posted any vacancies yet.</p>}
      {items && items.length > 0 && (
        <ul className="mt-3 divide-y rounded border">
          {items.map((job) => (
            <li key={job.id} className="p-3 text-sm">
              <Link href={`/vacancy/${job.id}`} className="font-medium underline">
                {job.title}
              </Link>
              <span className="ml-2 text-xs text-gray-500">({job.status})</span>
              <p className="text-gray-700">
                {job.company} · {job.type} · {job.work_mode}
                {job.location ? ` · ${job.location}` : ''}
              </p>
              {job.deadline && <p className="text-gray-500">Deadline: {job.deadline}</p>}
              <div className="mt-2 flex gap-3">
                <Link href={`/jobs/${job.id}/applicants`} className="underline">
                  Applicants
                </Link>
                {job.status === 'open' && (
                  <>
                    <Link href={`/jobs/${job.id}/edit`} className="underline">
                      Edit
                    </Link>
                    <button className="underline" disabled={busyId === job.id} onClick={() => close(job)}>
                      Close
                    </button>
                  </>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
