'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { ArrowRight, ArrowUpRight, ArrowClockwise, Plus, ShieldCheck } from '@phosphor-icons/react';
import { stagger } from '@/components/AuthShell';
import { FormAlert } from '@/components/FormField';
import { SECTION_LABEL } from '@/components/home/Band';
import VacancyRow from '@/components/VacancyRow';
import { ApiError, messageFor } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import {
  admin,
  dashboard,
  type ApplicantDashboard as ApplicantData,
  type ApplicationStatus,
  type OwnerDashboard as OwnerData,
} from '@/lib/endpoints';

/* ------------------------------------------------------------------ */
/* Shared                                                              */
/* ------------------------------------------------------------------ */

const EASE = 'ease-[cubic-bezier(0.16,1,0.3,1)]';
const BTN_BASE = `inline-flex min-h-11 items-center justify-center gap-2 rounded-full px-5 text-sm font-medium transition duration-300 ${EASE} active:translate-y-[1px] active:scale-[0.98] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-50`;
const BTN_PRIMARY = `${BTN_BASE} bg-zinc-900 text-zinc-50 shadow-[inset_0_1px_0_rgba(255,255,255,0.12)] hover:bg-zinc-800 focus-visible:outline-zinc-900`;
const BTN_OUTLINE = `${BTN_BASE} border border-zinc-200 bg-white text-zinc-900 hover:border-zinc-400 focus-visible:outline-zinc-900`;
const BTN_LIGHT = `${BTN_BASE} bg-zinc-50 text-zinc-900 hover:bg-white focus-visible:outline-white`;
const BTN_GHOST_DARK = `${BTN_BASE} border border-white/20 text-zinc-50 hover:border-white/50 focus-visible:outline-white`;
const CARD = 'rounded-[2.5rem] border border-zinc-200/60 bg-white p-8 shadow-[0_20px_40px_-15px_rgba(24,24,27,0.08)] md:p-10';

const STATUSES: { key: ApplicationStatus; label: string; dot: string }[] = [
  { key: 'submitted', label: 'Submitted', dot: 'bg-zinc-900' },
  { key: 'shortlisted', label: 'Shortlisted', dot: 'bg-zinc-700' },
  { key: 'accepted', label: 'Accepted', dot: 'bg-zinc-500' },
  { key: 'rejected', label: 'Rejected', dot: 'bg-zinc-400' },
  { key: 'withdrawn', label: 'Withdrawn', dot: 'bg-zinc-300' },
];

const STATUS_LABEL: Record<string, string> = Object.fromEntries(STATUSES.map((s) => [s.key, s.label]));

function errText(e: unknown, fallback: string): string {
  return e instanceof ApiError ? messageFor(e.code, e.message) : fallback;
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

function useLoad<T>(fetcher: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState('');
  const load = useCallback(() => {
    setError('');
    fetcher()
      .then(setData)
      .catch((e) => setError(errText(e, 'Could not load the dashboard.')));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(load, [load]);
  return { data, error, reload: load };
}

function PageHeader({ eyebrow, title, subtitle }: { eyebrow: string; title: string; subtitle: string }) {
  return (
    <header className="rise" style={stagger(0)}>
      <p className={SECTION_LABEL}>{eyebrow}</p>
      <h1 className="mt-3 max-w-[20ch] text-4xl font-semibold leading-[1.05] tracking-tighter text-zinc-900 md:text-5xl">{title}</h1>
      <p className="mt-4 max-w-[56ch] leading-relaxed text-zinc-500">{subtitle}</p>
    </header>
  );
}

function DashboardSkeleton() {
  return (
    <div aria-hidden className="mt-10 grid animate-pulse gap-6 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
      <div className="h-80 rounded-[2.5rem] bg-zinc-200/60" />
      <div className="h-80 rounded-[2.5rem] bg-zinc-200/60" />
    </div>
  );
}

function ErrorBox({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="mt-10 flex flex-col items-start gap-3">
      <FormAlert>{message}</FormAlert>
      <button type="button" onClick={onRetry} className={BTN_OUTLINE}>
        <ArrowClockwise size={16} weight="regular" />
        Try again
      </button>
    </div>
  );
}

/** Total plus a segmented bar and a legend, one row per status. */
function Pipeline({
  title,
  counts,
  footer,
}: {
  title: string;
  counts: Partial<Record<ApplicationStatus, number>>;
  footer?: React.ReactNode;
}) {
  const total = STATUSES.reduce((sum, s) => sum + (counts[s.key] ?? 0), 0);
  return (
    <section className={CARD} aria-label={title}>
      <h2 className={SECTION_LABEL}>{title}</h2>
      <p className="mt-5 flex items-baseline gap-3">
        <span className="text-7xl font-semibold leading-none tracking-tighter text-zinc-900 tabular-nums">{total}</span>
        <span className="text-zinc-500">{total === 1 ? 'application' : 'applications'} in total</span>
      </p>

      <div
        role="img"
        aria-label={STATUSES.map((s) => `${counts[s.key] ?? 0} ${s.label.toLowerCase()}`).join(', ')}
        className="mt-8 flex h-3 gap-0.5 overflow-hidden rounded-full bg-zinc-100"
      >
        {total > 0 &&
          STATUSES.map((s) => {
            const n = counts[s.key] ?? 0;
            return n > 0 ? <span key={s.key} className={s.dot} style={{ width: `${(n / total) * 100}%` }} /> : null;
          })}
      </div>

      <dl className="mt-8 grid grid-cols-2 gap-x-8 gap-y-5 sm:grid-cols-3">
        {STATUSES.map((s) => (
          <div key={s.key} className="flex items-center justify-between gap-3 border-b border-zinc-200 pb-3">
            <dt className="flex items-center gap-2.5 text-sm text-zinc-600">
              <span aria-hidden className={`h-2.5 w-2.5 rounded-full ${s.dot}`} />
              {s.label}
            </dt>
            <dd className="font-mono text-sm font-semibold tabular-nums text-zinc-900">{counts[s.key] ?? 0}</dd>
          </div>
        ))}
      </dl>

      {total === 0 && <p className="mt-6 text-sm text-zinc-500">Nothing here yet.</p>}
      {footer && <div className="mt-8">{footer}</div>}
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Alumni / admin                                                      */
/* ------------------------------------------------------------------ */

function AdminShortcut() {
  const [waiting, setWaiting] = useState<number | null>(null);
  useEffect(() => {
    admin
      .overview()
      .then((o) => setWaiting(o.alumni_awaiting_decision))
      .catch(() => setWaiting(null));
  }, []);

  return (
    <Link
      href="/admin"
      className={`group flex items-center justify-between gap-4 ${CARD} !p-6 transition duration-300 ${EASE} hover:border-zinc-400 active:scale-[0.99] md:!p-8`}
    >
      <span className="flex items-center gap-4">
        <span className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-zinc-100 text-zinc-700">
          <ShieldCheck size={22} weight="regular" />
        </span>
        <span>
          <span className="block font-semibold tracking-tight text-zinc-900">Admin panel</span>
          <span className="mt-0.5 block text-sm text-zinc-500">
            {waiting === null
              ? 'Verify alumni, moderate testimonials, manage users.'
              : waiting === 0
                ? 'No alumni are waiting for a decision.'
                : `${waiting} alumni ${waiting === 1 ? 'is' : 'are'} waiting for a decision.`}
          </span>
        </span>
      </span>
      <ArrowUpRight
        size={20}
        weight="regular"
        className={`shrink-0 text-zinc-500 transition-transform duration-300 ${EASE} group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-zinc-900`}
      />
    </Link>
  );
}

function OwnerDashboard({ isAdmin }: { isAdmin: boolean }) {
  const { data, error, reload } = useLoad<OwnerData>(() => dashboard.owner());

  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return <DashboardSkeleton />;

  const open = data.jobs.open ?? 0;
  const closed = data.jobs.closed ?? 0;

  return (
    <div className="mt-10 grid items-start gap-6 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
      <div className="rise" style={stagger(1)}>
        <Pipeline
          title="Applications received"
          counts={data.applications}
          footer={
            <p className="flex items-center gap-3 rounded-full bg-zinc-100 px-5 py-3 text-sm text-zinc-700">
              <span className="font-mono text-base font-semibold tabular-nums text-zinc-900">{data.new_applications}</span>
              new in the last 7 days
            </p>
          }
        />
      </div>

      <div className="flex flex-col gap-6">
        <section
          className="rise relative overflow-hidden rounded-[2.5rem] border border-white/10 bg-zinc-950 p-8 text-zinc-50 shadow-[inset_0_1px_0_rgba(255,255,255,0.1)] md:p-10"
          style={stagger(2)}
          aria-label="My vacancies"
        >
          <div
            aria-hidden
            className="absolute inset-x-0 top-0 h-48 bg-[radial-gradient(ellipse_at_top_left,rgba(255,255,255,0.08),transparent_70%)]"
          />
          <h2 className="relative text-xs font-semibold uppercase tracking-[0.14em] text-zinc-400">My vacancies</h2>
          <div className="relative mt-5 flex items-end gap-8">
            <p>
              <span className="block text-7xl font-semibold leading-none tracking-tighter tabular-nums">{open}</span>
              <span className="mt-2 block text-sm text-zinc-400">open</span>
            </p>
            <p className="pb-1">
              <span className="block text-3xl font-semibold leading-none tracking-tighter tabular-nums text-zinc-300">{closed}</span>
              <span className="mt-2 block text-sm text-zinc-500">closed</span>
            </p>
          </div>
          <div className="relative mt-8 flex flex-wrap gap-3">
            <Link href="/jobs/new" className={BTN_LIGHT}>
              <Plus size={16} weight="bold" />
              Post a vacancy
            </Link>
            <Link href="/jobs" className={BTN_GHOST_DARK}>
              Manage vacancies
            </Link>
          </div>
        </section>

        {isAdmin && (
          <div className="rise" style={stagger(3)}>
            <AdminShortcut />
          </div>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Applicant                                                           */
/* ------------------------------------------------------------------ */

const DOCS: { key: 'cv' | 'ktp' | 'intro_video'; label: string; hint: string; required: boolean }[] = [
  { key: 'cv', label: 'CV', hint: 'PDF, required to apply', required: true },
  { key: 'ktp', label: 'ID card', hint: 'Shown only to vacancy owners', required: false },
  { key: 'intro_video', label: 'Intro video', hint: 'MP4, optional', required: false },
];

function StatusBadge({ status }: { status: string }) {
  const tone =
    status === 'accepted'
      ? 'bg-zinc-900 text-zinc-50'
      : status === 'rejected' || status === 'withdrawn'
        ? 'bg-zinc-200/70 text-zinc-600'
        : 'border border-zinc-300 text-zinc-700';
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium uppercase tracking-wider ${tone}`}>
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

function SectionHead({ title, href, linkLabel }: { title: string; href: string; linkLabel: string }) {
  return (
    <div className="flex items-end justify-between gap-4">
      <h2 className="text-2xl font-semibold tracking-tight text-zinc-900">{title}</h2>
      <Link
        href={href}
        className="group inline-flex items-center gap-1.5 text-sm font-medium text-zinc-900 underline-offset-4 hover:underline"
      >
        {linkLabel}
        <ArrowRight size={14} weight="bold" className={`transition-transform duration-300 ${EASE} group-hover:translate-x-0.5`} />
      </Link>
    </div>
  );
}

function ApplicantDashboard() {
  const { data, error, reload } = useLoad<ApplicantData>(() => dashboard.applicant());

  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return <DashboardSkeleton />;

  return (
    <div className="mt-10 flex flex-col gap-16">
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <div className="rise" style={stagger(1)}>
          <Pipeline
            title="Your applications"
            counts={data.applications}
            footer={
              <Link href="/applications" className={BTN_OUTLINE}>
                All my applications
              </Link>
            }
          />
        </div>

        <section className={`rise ${CARD}`} style={stagger(2)} aria-label="Documents">
          <h2 className={SECTION_LABEL}>Documents</h2>
          <ul className="mt-5 divide-y divide-zinc-200 border-y border-zinc-200">
            {DOCS.map((d) => {
              const n = data.documents[d.key] ?? 0;
              return (
                <li key={d.key} className="flex items-center justify-between gap-4 py-4">
                  <div className="min-w-0">
                    <p className="font-medium text-zinc-900">{d.label}</p>
                    <p className="mt-0.5 text-sm text-zinc-500">{d.hint}</p>
                  </div>
                  {n > 0 ? (
                    <span className="rounded-full bg-zinc-900 px-2.5 py-0.5 text-[11px] font-medium uppercase tracking-wider text-zinc-50">
                      {n} uploaded
                    </span>
                  ) : (
                    <span className="rounded-full border border-zinc-300 px-2.5 py-0.5 text-[11px] font-medium uppercase tracking-wider text-zinc-600">
                      {d.required ? 'Missing' : 'None'}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
          <div className="mt-8">
            <Link href="/documents" className={BTN_PRIMARY}>
              Manage documents
            </Link>
          </div>
        </section>
      </div>

      <section className="rise" style={stagger(3)} aria-label="Recent applications">
        <SectionHead title="Recent applications" href="/applications" linkLabel="View all" />
        {data.recent_applications.length === 0 ? (
          <div className="mt-6 flex flex-col items-start gap-4 rounded-[2rem] border border-dashed border-zinc-300 px-8 py-10">
            <p className="max-w-[44ch] text-zinc-500">You have not applied to anything yet. Find a vacancy posted by an alumnus and apply.</p>
            <Link href="/vacancy" className={BTN_PRIMARY}>
              Browse vacancies
            </Link>
          </div>
        ) : (
          <ul className="mt-6 divide-y divide-zinc-200 border-y border-zinc-200">
            {data.recent_applications.map((a) => (
              <li key={a.id}>
                <Link
                  href={`/applications/${a.id}`}
                  className="group grid gap-3 px-2 py-5 transition-colors duration-300 hover:bg-white/70 sm:grid-cols-[1fr_auto] sm:items-center"
                >
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-center gap-3 text-lg font-semibold tracking-tight text-zinc-900">
                      {a.job.title}
                      <StatusBadge status={a.status} />
                    </p>
                    <p className="mt-1 text-sm text-zinc-500">{a.job.company}</p>
                  </div>
                  <div className="flex items-center gap-4 text-zinc-500">
                    <span className="font-mono text-xs">Applied {formatDate(a.created_at)}</span>
                    <ArrowUpRight
                      size={20}
                      weight="regular"
                      className={`transition-transform duration-300 ${EASE} group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-zinc-900`}
                    />
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rise" style={stagger(4)} aria-label="Recommended for you">
        <SectionHead title="Recommended for you" href="/vacancy" linkLabel="All vacancies" />
        {data.matches.length === 0 ? (
          <p className="mt-6 rounded-[2rem] border border-dashed border-zinc-300 px-8 py-10 text-zinc-500">
            No matching vacancies right now.{' '}
            <Link href="/profile" className="font-medium text-zinc-900 underline underline-offset-4">
              Add skills to your profile
            </Link>{' '}
            to get recommendations.
          </p>
        ) : (
          <ul className="mt-6 divide-y divide-zinc-200 border-y border-zinc-200">
            {data.matches.map((m, i) => (
              <VacancyRow
                key={m.job.id}
                job={m.job}
                index={i}
                extra={
                  <p className="mt-3 font-mono text-xs text-zinc-500">
                    {m.score} matching {m.score === 1 ? 'skill' : 'skills'}: {m.matched_skills.map((s) => s.name).join(', ')}
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

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

export default function DashboardPage() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div aria-hidden className="flex animate-pulse flex-col gap-5 py-4">
        <div className="h-4 w-24 rounded-full bg-zinc-200/70" />
        <div className="h-12 w-80 max-w-full rounded-full bg-zinc-200/70" />
        <DashboardSkeleton />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="py-4">
        <h1 className="text-3xl font-semibold tracking-tight text-zinc-900">Dashboard</h1>
        <p className="mt-3 text-zinc-500">
          Please{' '}
          <Link href="/login" className="font-medium text-zinc-900 underline underline-offset-4">
            sign in
          </Link>{' '}
          to see your dashboard.
        </p>
      </div>
    );
  }

  if (user.status !== 'active') {
    return (
      <div className="py-4">
        <h1 className="text-3xl font-semibold tracking-tight text-zinc-900">Dashboard</h1>
        <p className="mt-3 max-w-[52ch] text-zinc-500">
          Your account is not active yet, so there is no dashboard.{' '}
          <Link href="/profile" className="font-medium text-zinc-900 underline underline-offset-4">
            Go to your profile
          </Link>
        </p>
      </div>
    );
  }

  const applicant = user.role === 'applicant';
  return (
    <div className="py-4">
      <PageHeader
        eyebrow="Dashboard"
        title={`Welcome back, ${user.username}`}
        subtitle={
          applicant
            ? 'Track your applications and find vacancies that match your skills.'
            : 'See how your vacancies and applicants are doing.'
        }
      />
      {applicant ? <ApplicantDashboard /> : <OwnerDashboard isAdmin={user.role === 'admin'} />}
    </div>
  );
}