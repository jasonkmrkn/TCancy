'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import type { Job } from '@/components/JobCard';
import { api, ApiError } from '@/lib/api';
import { useAuth } from '@/lib/auth';

type Item = { id: string; status: string; created_at: string; job: Job };

export default function ApplicationsPage() {
  const { user, loading } = useAuth();
  const [items, setItems] = useState<Item[] | null>(null);
  const [error, setError] = useState('');
  const allowed = user?.role === 'applicant' && user.status === 'active';

  useEffect(() => {
    if (!allowed) return;
    api<Item[]>('/me/applications')
      .then(setItems)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load applications.'));
  }, [allowed]);

  if (loading) return <p className="text-sm text-gray-600">Loading...</p>;
  if (!allowed) {
    return (
      <p className="text-sm">
        Only active applicants have applications.{' '}
        {!user && (
          <Link href="/login" className="underline">
            Sign in
          </Link>
        )}
      </p>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold">My applications</h1>
      {error && <p className="mt-3 text-sm text-red-700">{error}</p>}
      {!items && !error && <p className="mt-3 text-sm text-gray-600">Loading...</p>}
      {items && items.length === 0 && (
        <p className="mt-3 text-sm">
          You have not applied to anything yet.{' '}
          <Link href="/vacancy" className="underline">
            Browse vacancies
          </Link>
        </p>
      )}
      {items && items.length > 0 && (
        <ul className="mt-3 divide-y rounded border">
          {items.map((a) => (
            <li key={a.id} className="p-3 text-sm">
              <Link href={`/applications/${a.id}`} className="font-medium underline">
                {a.job.title}
              </Link>
              <p className="text-gray-700">{a.job.company}</p>
              <p className="text-gray-500">
                Status: {a.status} · Applied {a.created_at.slice(0, 10)}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
