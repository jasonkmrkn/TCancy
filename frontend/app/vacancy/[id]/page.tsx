'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import { ArrowLeft, CalendarBlank, Clock, MapPin, Buildings, Briefcase, Laptop } from '@phosphor-icons/react';
import { stagger } from '@/components/AuthShell';
import ApplyForm from '@/components/ApplyForm';
import { FormAlert } from '@/components/FormField';
import { SECTION_LABEL } from '@/components/home/Band';
import type { Job } from '@/components/JobCard';
import { BTN_OUTLINE, BTN_PRIMARY, Pill } from '@/components/ui';
import { api, ApiError } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { modeLabel, typeLabel } from '@/lib/labels';

type JobDetail = Job & { description: string; requirements: string | null };

function parseDate(value: string): Date {
  return new Date(value.length === 10 ? value + 'T23:59:59' : value);
}

function formatDate(value: string): string {
  return new Date(value.length === 10 ? value + 'T00:00:00' : value).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

function daysLeft(deadline: string): number {
  return Math.ceil((parseDate(deadline).getTime() - Date.now()) / 86_400_000);
}

function Fact({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start gap-4 py-4">
      <span aria-hidden className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-full bg-zinc-100 text-zinc-700">
        <Icon size={18} />
      </span>
      <div className="min-w-0">
        <dt className="text-xs uppercase tracking-wider text-zinc-500">{label}</dt>
        <dd className="mt-0.5 font-medium text-zinc-900">{value}</dd>
      </div>
    </div>
  );
}

function PageSkeleton() {
  return (
    <div aria-hidden className="animate-pulse py-4">
      <div className="h-4 w-32 rounded-full bg-zinc-200/70" />
      <div className="mt-8 h-12 w-96 max-w-full rounded-full bg-zinc-200/70" />
      <div className="mt-4 h-5 w-72 max-w-full rounded-full bg-zinc-200/70" />
      <div className="mt-10 grid gap-6 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <div className="h-96 rounded-[2.5rem] bg-zinc-200/60" />
        <div className="h-96 rounded-[2.5rem] bg-zinc-200/60" />
      </div>
    </div>
  );
}

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

  const back = (
    <Link
      href="/vacancy"
      className="inline-flex items-center gap-1.5 text-sm font-medium text-zinc-600 transition-colors hover:text-zinc-900"
    >
      <ArrowLeft size={14} weight="bold" />
      All vacancies
    </Link>
  );

  if (error) {
    return (
      <div className="py-4">
        {back}
        <div className="mt-8 flex flex-col items-start gap-4">
          <FormAlert>{error}</FormAlert>
          <Link href="/vacancy" className={BTN_OUTLINE}>
            Browse vacancies
          </Link>
        </div>
      </div>
    );
  }

  if (!job) return <PageSkeleton />;

  const closed = job.status === 'closed';
  const left = job.deadline ? daysLeft(job.deadline) : null;
  const expired = !closed && left !== null && left < 0;
  const isApplicant = user?.role === 'applicant' && user.status === 'active';

  return (
    <div className="py-4">
      {back}

      <header className="rise mt-8" style={stagger(0)}>
        <div className="flex flex-wrap items-center gap-3">
          <p className={SECTION_LABEL}>{job.company}</p>
          <Pill tone={closed ? 'muted' : 'solid'}>{closed ? 'Closed' : 'Open'}</Pill>
        </div>
        <h1 className="mt-3 max-w-[22ch] text-4xl font-semibold leading-[1.05] tracking-tighter text-zinc-900 md:text-6xl">
          {job.title}
        </h1>
        <p className="mt-5 flex flex-wrap items-center gap-x-3 gap-y-1 text-zinc-500">
          <span>{typeLabel(job.type)}</span>
          <span aria-hidden>·</span>
          <span>{modeLabel(job.work_mode)}</span>
          {job.location && (
            <>
              <span aria-hidden>·</span>
              <span className="inline-flex items-center gap-1">
                <MapPin size={16} />
                {job.location}
              </span>
            </>
          )}
        </p>
      </header>

      <div className="mt-12 grid items-start gap-6 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        {/* Description */}
        <article
          className="rise rounded-[2.5rem] border border-zinc-200/60 bg-white p-8 shadow-[0_20px_40px_-15px_rgba(24,24,27,0.08)] md:p-10"
          style={stagger(1)}
        >
          <section>
            <h2 className={SECTION_LABEL}>About the role</h2>
            <p className="mt-5 max-w-[68ch] whitespace-pre-wrap leading-relaxed text-zinc-700">{job.description}</p>
          </section>

          {job.requirements && (
            <section className="mt-10 border-t border-zinc-200 pt-10">
              <h2 className={SECTION_LABEL}>Requirements</h2>
              <p className="mt-5 max-w-[68ch] whitespace-pre-wrap leading-relaxed text-zinc-700">{job.requirements}</p>
            </section>
          )}

          {job.skills.length > 0 && (
            <section className="mt-10 border-t border-zinc-200 pt-10">
              <h2 className={SECTION_LABEL}>Skills</h2>
              <ul className="mt-5 flex flex-wrap gap-2">
                {job.skills.map((s) => (
                  <li key={s.id} className="rounded-full border border-zinc-200 bg-zinc-50 px-4 py-1.5 text-sm text-zinc-700">
                    {s.name}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </article>

        {/* Sidebar */}
        <aside className="rise flex flex-col gap-6 lg:sticky lg:top-24" style={stagger(2)}>
          <section className="order-last rounded-[2.5rem] border border-zinc-200/60 bg-white px-8 py-4 lg:order-none shadow-[0_20px_40px_-15px_rgba(24,24,27,0.08)]">
            <h2 className="sr-only">Overview</h2>
            <dl className="divide-y divide-zinc-200">
              <Fact icon={Buildings} label="Company" value={job.company} />
              <Fact icon={Briefcase} label="Type" value={typeLabel(job.type)} />
              <Fact icon={Laptop} label="Work mode" value={modeLabel(job.work_mode)} />
              {job.location && <Fact icon={MapPin} label="Location" value={job.location} />}
              <Fact
                icon={CalendarBlank}
                label="Deadline"
                value={
                  job.deadline ? (
                    <>
                      {formatDate(job.deadline)}
                      {!closed && left !== null && (
                        <span className={`ml-2 text-sm ${left <= 3 ? 'font-semibold text-zinc-900' : 'font-normal text-zinc-500'}`}>
                          {left < 0 ? 'passed' : left === 0 ? 'today' : left === 1 ? '1 day left' : `${left} days left`}
                        </span>
                      )}
                    </>
                  ) : (
                    <span className="font-normal text-zinc-500">No deadline</span>
                  )
                }
              />
              <Fact icon={Clock} label="Posted" value={formatDate(job.created_at)} />
            </dl>
          </section>

          {closed && (
            <p className="rounded-[2rem] border border-dashed border-zinc-300 px-8 py-6 text-zinc-500">
              This vacancy is closed and no longer accepts applications.
            </p>
          )}

          {!closed && expired && (
            <p className="rounded-[2rem] border border-dashed border-zinc-300 px-8 py-6 text-zinc-500">
              The deadline for this vacancy has passed.
            </p>
          )}

          {!closed && !expired && !user && (
            <section className="relative overflow-hidden rounded-[2.5rem] bg-zinc-950 p-8 text-zinc-50 shadow-[inset_0_1px_0_rgba(255,255,255,0.1)]">
              <div
                aria-hidden
                className="absolute inset-x-0 top-0 h-40 bg-[radial-gradient(ellipse_at_top_left,rgba(255,255,255,0.08),transparent_70%)]"
              />
              <h2 className="relative text-xl font-semibold tracking-tight">Interested?</h2>
              <p className="relative mt-2 text-sm leading-relaxed text-zinc-400">
                Sign in as an applicant to send your CV and a short note to the alumnus who posted this.
              </p>
              <div className="relative mt-6 flex flex-wrap gap-3">
                <Link
                  href="/login"
                  className="inline-flex min-h-11 items-center justify-center rounded-full bg-zinc-50 px-5 text-sm font-medium text-zinc-900 transition duration-300 hover:bg-white active:scale-[0.98]"
                >
                  Sign in to apply
                </Link>
                <Link
                  href="/register"
                  className="inline-flex min-h-11 items-center justify-center rounded-full border border-white/20 px-5 text-sm font-medium text-zinc-50 transition duration-300 hover:border-white/50 active:scale-[0.98]"
                >
                  Create account
                </Link>
              </div>
            </section>
          )}

          {!closed && !expired && user && !isApplicant && (
            <p className="rounded-[2rem] border border-dashed border-zinc-300 px-8 py-6 text-zinc-500">
              Only applicant accounts can apply to vacancies.
            </p>
          )}

          {!closed && !expired && isApplicant && <ApplyForm jobId={job.id} />}
        </aside>
      </div>
    </div>
  );
}