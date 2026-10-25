'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { api, ApiError } from '@/lib/api';

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

export default function LatestJobs() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api<{ items: Job[] }>('/jobs', { query: { limit: 6 } })
      .then((r) => setJobs(r.items))
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load vacancies.'));
  }, []);

  return (
    <section className="mt-8">
      <div className="flex items-baseline justify-between">
        <h2 className="text-xl font-semibold">Latest vacancies</h2>
        <Link href="/vacancy" className="text-sm underline">
          View all
        </Link>
      </div>
      {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
      {!error && jobs === null && <p className="mt-2 text-sm text-gray-600">Loading...</p>}
      {jobs && jobs.length === 0 && <p className="mt-2 text-sm text-gray-600">No vacancies yet.</p>}
      {jobs && jobs.length > 0 && (
        <ul className="mt-3 divide-y rounded border">
          {jobs.map((j) => (
            <li key={j.id} className="p-3 text-sm">
              <Link href={`/vacancy/${j.id}`} className="font-medium underline">
                {j.title}
              </Link>
              <p className="text-gray-700">
                {j.company} · {j.type} · {j.work_mode}
                {j.location ? ` · ${j.location}` : ''}
              </p>
              {j.deadline && <p className="text-gray-500">Deadline: {j.deadline}</p>}
              {j.skills.length > 0 && <p className="text-gray-500">{j.skills.map((s) => s.name).join(', ')}</p>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
