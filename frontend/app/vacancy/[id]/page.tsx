'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import ApplyForm from '@/components/ApplyForm';
import { Job } from '@/components/JobCard';
import { api, ApiError } from '@/lib/api';
import { useAuth } from '@/lib/auth';

type JobDetail = Job & { description: string; requirements: string };

export default function VacancyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const [job, setJob] = useState<JobDetail | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api<JobDetail>(`/jobs/${id}`)
      .then(setJob)
      .catch((e) => {
        if (e instanceof ApiError && e.code === 'JOB_NOT_FOUND') setError('Vacancy not found.');
        else setError(e instanceof ApiError ? e.message : 'Could not load the vacancy.');
      });
  }, [id]);

  return (
    <div>
      <Link href="/vacancy" className="text-sm underline">
        Back to vacancies
      </Link>
      {error && <p className="mt-4 text-sm text-red-700">{error}</p>}
      {!error && !job && <p className="mt-4 text-sm text-gray-600">Loading...</p>}
      {job && (
        <article className="mt-4">
          <h1 className="text-2xl font-semibold">{job.title}</h1>
          <p className="text-gray-700">
            {job.company} · {job.type} · {job.work_mode}
            {job.location ? ` · ${job.location}` : ''}
          </p>
          <p className="mt-1 text-sm text-gray-500">
            Status: {job.status}
            {job.deadline ? ` · Deadline: ${job.deadline}` : ''}
          </p>
          {job.skills.length > 0 && (
            <p className="mt-1 text-sm text-gray-500">Skills: {job.skills.map((s) => s.name).join(', ')}</p>
          )}
          <h2 className="mt-4 font-semibold">Description</h2>
          <p className="whitespace-pre-wrap text-sm">{job.description}</p>
          <h2 className="mt-4 font-semibold">Requirements</h2>
          <p className="whitespace-pre-wrap text-sm">{job.requirements}</p>
          {job.status === 'open' && !user && (
            <p className="mt-4 text-sm">
              <Link href="/login" className="underline">
                Sign in
              </Link>{' '}
              as an applicant to apply.
            </p>
          )}
          {job.status === 'open' && user?.role === 'applicant' && user.status === 'active' && (
            <ApplyForm jobId={job.id} />
          )}
          {job.status === 'closed' && <p className="mt-4 text-sm text-gray-600">This vacancy is closed.</p>}
        </article>
      )}
    </div>
  );
}
