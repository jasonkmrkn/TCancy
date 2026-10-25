'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import JobCard, { type Job } from '@/components/JobCard';
import { api, ApiError } from '@/lib/api';
import { useAuth } from '@/lib/auth';

type Counts = Record<string, number>;

type ApplicantData = {
  applications: Counts;
  documents: Counts;
  recent_applications: { id: string; status: string; created_at: string; job: Job }[];
  matches: { job: Job; score: number; matched_skills: { id: string; name: string }[] }[];
};

type OwnerData = {
  jobs: Counts;
  applications: Counts;
  new_applications: number;
};

const APPLICATION_STATUSES = ['submitted', 'shortlisted', 'accepted', 'rejected', 'withdrawn'];
const DOCUMENT_LABELS: [string, string][] = [
  ['cv', 'CV'],
  ['ktp', 'ID card'],
  ['intro_video', 'Intro video'],
];

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded border p-3">
      <p className="text-2xl font-semibold">{value}</p>
      <p className="text-sm text-gray-600">{label}</p>
    </div>
  );
}

function ApplicantDashboard() {
  const [data, setData] = useState<ApplicantData | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api<ApplicantData>('/me/dashboard')
      .then(setData)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load the dashboard.'));
  }, []);

  if (error) return <p className="mt-3 text-sm text-red-700">{error}</p>;
  if (!data) return <p className="mt-3 text-sm text-gray-600">Loading...</p>;

  return (
    <div className="mt-4 space-y-6">
      <section>
        <h2 className="text-lg font-semibold">Applications</h2>
        <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-5">
          {APPLICATION_STATUSES.map((s) => (
            <Stat key={s} label={s} value={data.applications[s] ?? 0} />
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-lg font-semibold">Documents</h2>
        <div className="mt-2 grid grid-cols-3 gap-3">
          {DOCUMENT_LABELS.map(([key, label]) => (
            <Stat key={key} label={label} value={data.documents[key] ?? 0} />
          ))}
        </div>
        <p className="mt-2 text-sm">
          <Link href="/documents" className="underline">
            Manage documents
          </Link>
        </p>
      </section>

      <section>
        <h2 className="text-lg font-semibold">Recent applications</h2>
        {data.recent_applications.length === 0 ? (
          <p className="mt-2 text-sm">
            You have not applied to anything yet.{' '}
            <Link href="/vacancy" className="underline">
              Browse vacancies
            </Link>
          </p>
        ) : (
          <ul className="mt-2 divide-y rounded border">
            {data.recent_applications.map((a) => (
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
        <p className="mt-2 text-sm">
          <Link href="/applications" className="underline">
            All my applications
          </Link>
        </p>
      </section>

      <section>
        <h2 className="text-lg font-semibold">Recommended for you</h2>
        {data.matches.length === 0 ? (
          <p className="mt-2 text-sm text-gray-700">
            No matching vacancies right now. Add skills to your profile to get recommendations.
          </p>
        ) : (
          <ul className="mt-2 divide-y rounded border">
            {data.matches.map((m) => (
              <JobCard
                key={m.job.id}
                job={m.job}
                extra={
                  <p className="text-gray-500">
                    Match score: {m.score} · {m.matched_skills.map((s) => s.name).join(', ')}
                  </p>
                }
              />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function OwnerDashboard({ isAdmin }: { isAdmin: boolean }) {
  const [data, setData] = useState<OwnerData | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api<OwnerData>('/owner/dashboard')
      .then(setData)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load the dashboard.'));
  }, []);

  if (error) return <p className="mt-3 text-sm text-red-700">{error}</p>;
  if (!data) return <p className="mt-3 text-sm text-gray-600">Loading...</p>;

  return (
    <div className="mt-4 space-y-6">
      <section>
        <h2 className="text-lg font-semibold">My vacancies</h2>
        <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="open" value={data.jobs.open ?? 0} />
          <Stat label="closed" value={data.jobs.closed ?? 0} />
        </div>
        <p className="mt-2 text-sm">
          <Link href="/jobs" className="underline">
            Manage vacancies
          </Link>
          {' · '}
          <Link href="/jobs/new" className="underline">
            Post a vacancy
          </Link>
        </p>
      </section>

      <section>
        <h2 className="text-lg font-semibold">Applications received</h2>
        <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-5">
          {APPLICATION_STATUSES.map((s) => (
            <Stat key={s} label={s} value={data.applications[s] ?? 0} />
          ))}
        </div>
        <p className="mt-2 text-sm text-gray-700">
          New applications in the last 7 days: <span className="font-medium">{data.new_applications}</span>
        </p>
      </section>

      {isAdmin && (
        <p className="text-sm">
          <Link href="/admin" className="underline">
            Go to the admin page
          </Link>
        </p>
      )}
    </div>
  );
}

export default function DashboardPage() {
  const { user, loading } = useAuth();

  if (loading) return <p className="text-sm text-gray-600">Loading...</p>;
  if (!user) {
    return (
      <p className="text-sm">
        Please{' '}
        <Link href="/login" className="underline">
          sign in
        </Link>{' '}
        to see your dashboard.
      </p>
    );
  }
  if (user.status !== 'active') {
    return (
      <p className="text-sm">
        Your account is not active yet, so there is no dashboard.{' '}
        <Link href="/profile" className="underline">
          Go to your profile
        </Link>
      </p>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold">Dashboard</h1>
      {user.role === 'applicant' ? <ApplicantDashboard /> : <OwnerDashboard isAdmin={user.role === 'admin'} />}
    </div>
  );
}
