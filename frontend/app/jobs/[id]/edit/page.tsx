'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import JobForm, { type JobValues } from '@/components/JobForm';
import { NotAllowed, useIsOwnerRole } from '@/components/OwnerGate';
import { api, ApiError } from '@/lib/api';

type JobDetail = {
  title: string;
  company: string;
  type: string;
  work_mode: string;
  location: string | null;
  description: string;
  requirements: string | null;
  deadline: string | null;
  status: string;
  skills: { id: string; name: string }[];
};

export default function EditJobPage() {
  const { id } = useParams<{ id: string }>();
  const { loading, allowed } = useIsOwnerRole();
  const [job, setJob] = useState<JobDetail | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!allowed) return;
    api<JobDetail>(`/jobs/${id}`)
      .then(setJob)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load the vacancy.'));
  }, [allowed, id]);

  if (loading) return <p className="text-sm text-gray-600">Loading...</p>;
  if (!allowed) return <NotAllowed />;

  const initial: JobValues | null = job && {
    title: job.title,
    company: job.company,
    type: job.type,
    work_mode: job.work_mode,
    location: job.location ?? '',
    description: job.description,
    requirements: job.requirements ?? '',
    deadline: job.deadline ?? '',
    skill_ids: job.skills.map((s) => s.id),
  };

  return (
    <div>
      <Link href="/jobs" className="text-sm underline">
        Back to my vacancies
      </Link>
      <h1 className="mt-2 text-2xl font-semibold">Edit vacancy</h1>
      {error && <p className="mt-3 text-sm text-red-700">{error}</p>}
      {!job && !error && <p className="mt-3 text-sm text-gray-600">Loading...</p>}
      {job?.status === 'closed' && (
        <p className="mt-3 text-sm text-red-700">This vacancy is closed and cannot be edited.</p>
      )}
      {initial && job?.status === 'open' && <JobForm jobId={id} initial={initial} />}
    </div>
  );
}
