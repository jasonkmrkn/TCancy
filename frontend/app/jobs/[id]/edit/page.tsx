'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import { ArrowLeft } from '@phosphor-icons/react';
import { FormAlert } from '@/components/FormField';
import JobForm, { type JobValues } from '@/components/JobForm';
import { NotAllowed, useIsOwnerRole } from '@/components/OwnerGate';
import { PageHeader } from '@/components/ui';
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

  if (loading) {
    return (
      <div aria-hidden className="flex animate-pulse flex-col gap-5 py-4">
        <div className="h-4 w-24 rounded-full bg-zinc-200/70" />
        <div className="h-12 w-80 max-w-full rounded-full bg-zinc-200/70" />
        <div className="mt-6 h-96 rounded-[2.5rem] bg-zinc-200/60" />
      </div>
    );
  }
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
    <div className="py-4">
      <Link
        href="/jobs"
        className="mb-6 inline-flex items-center gap-1.5 text-sm font-medium text-zinc-600 transition-colors hover:text-zinc-900"
      >
        <ArrowLeft size={14} weight="bold" />
        My vacancies
      </Link>
      <PageHeader eyebrow="Vacancies" title="Edit vacancy" subtitle="Changes are visible to students as soon as you save." />
      {error && (
        <div className="mt-10">
          <FormAlert>{error}</FormAlert>
        </div>
      )}
      {!job && !error && <div aria-hidden className="mt-10 h-96 animate-pulse rounded-[2.5rem] bg-zinc-200/60" />}
      {job?.status === 'closed' && (
        <div className="mt-10">
          <FormAlert>This vacancy is closed and cannot be edited.</FormAlert>
        </div>
      )}
      {initial && job?.status === 'open' && <JobForm jobId={id} initial={initial} />}
    </div>
  );
}