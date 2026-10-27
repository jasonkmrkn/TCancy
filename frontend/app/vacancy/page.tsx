'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowClockwise, MagnifyingGlass, MapPin, SlidersHorizontal } from '@phosphor-icons/react';
import { stagger } from '@/components/AuthShell';
import Chip from '@/components/Chip';
import { inputClass } from '@/components/FormField';
import { SECTION_LABEL } from '@/components/home/Band';
import VacancyRow, { type RowJob } from '@/components/VacancyRow';
import { api, ApiError } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { modeLabel, typeLabel } from '@/lib/labels';

type Skill = { id: string; name: string };
type Match = { job: RowJob; score: number; matched_skills: Skill[] };

type Filters = { q: string; location: string; type: string; work_mode: string; skill: string[] };
const EMPTY: Filters = { q: '', location: '', type: '', work_mode: '', skill: [] };

const TYPES = ['internship', 'fulltime', 'parttime', 'contract'];
const MODES = ['onsite', 'hybrid', 'remote'];
const MAX_SKILLS = 20;
const SKILLS_COLLAPSED = 12;

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

function RowSkeleton() {
  return (
    <li aria-hidden className="animate-pulse px-2 py-6">
      <div className="h-5 w-64 max-w-full rounded-full bg-zinc-200/70" />
      <div className="mt-3 h-4 w-80 max-w-full rounded-full bg-zinc-200/70" />
      <div className="mt-4 flex gap-2">
        <div className="h-6 w-16 rounded-full bg-zinc-200/70" />
        <div className="h-6 w-20 rounded-full bg-zinc-200/70" />
        <div className="h-6 w-14 rounded-full bg-zinc-200/70" />
      </div>
    </li>
  );
}

function FilterGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <fieldset className="flex flex-col gap-3">
      <legend className={`${SECTION_LABEL} mb-3`}>{label}</legend>
      <div className="flex flex-wrap gap-2">{children}</div>
    </fieldset>
  );
}

export default function VacancyPage() {
  const { user } = useAuth();
  const [form, setForm] = useState<Filters>(EMPTY);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [showAllSkills, setShowAllSkills] = useState(false);
  const [jobs, setJobs] = useState<RowJob[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState('');
  const [matches, setMatches] = useState<Match[]>([]);
  const reqRef = useRef(0);

  // Chips apply instantly; the two text inputs wait for a short pause in typing.
  const q = useDebounced(form.q.trim(), 350);
  const location = useDebounced(form.location.trim(), 350);
  const applied = useMemo<Filters>(
    () => ({ q, location, type: form.type, work_mode: form.work_mode, skill: form.skill }),
    [q, location, form.type, form.work_mode, form.skill],
  );

  useEffect(() => {
    api<Skill[]>('/skills').then(setSkills).catch(() => setSkills([]));
  }, []);

  const isApplicant = user?.role === 'applicant' && user.status === 'active';
  useEffect(() => {
    if (!isApplicant) {
      setMatches([]);
      return;
    }
    api<{ items: Match[] }>('/me/matches', { query: { limit: 5 } })
      .then((r) => setMatches(r.items))
      .catch(() => setMatches([]));
  }, [isApplicant]);

  const load = useCallback(async (f: Filters, after: string | null) => {
    const id = ++reqRef.current; // ignore responses that arrive after a newer request
    if (after) setLoadingMore(true);
    else setLoading(true);
    setError('');
    try {
      const r = await api<{ items: RowJob[]; next_cursor: string | null }>('/jobs', {
        query: { ...f, limit: 20, cursor: after },
      });
      if (id !== reqRef.current) return;
      setJobs((prev) => (after ? [...prev, ...r.items] : r.items));
      setCursor(r.next_cursor);
    } catch (e) {
      if (id !== reqRef.current) return;
      if (!after) {
        setJobs([]);
        setCursor(null);
      }
      setError(e instanceof ApiError ? e.message : 'Could not load vacancies.');
    } finally {
      if (id === reqRef.current) {
        setLoading(false);
        setLoadingMore(false);
      }
    }
  }, []);

  useEffect(() => {
    load(applied, null);
  }, [applied, load]);

  const hasFilters = Boolean(form.q || form.location || form.type || form.work_mode || form.skill.length);

  function toggleSkill(id: string) {
    setForm((f) => {
      if (f.skill.includes(id)) return { ...f, skill: f.skill.filter((s) => s !== id) };
      if (f.skill.length >= MAX_SKILLS) return f;
      return { ...f, skill: [...f.skill, id] };
    });
  }

  const visibleSkills = showAllSkills ? skills : skills.slice(0, SKILLS_COLLAPSED);
  const firstLoad = loading && jobs.length === 0 && !error;
  const summary = firstLoad
    ? 'Loading vacancies'
    : error
      ? 'Failed to load'
      : `${jobs.length}${cursor ? '+' : ''} ${jobs.length === 1 ? 'vacancy' : 'vacancies'}`;

  return (
    <div className="py-4">
      <header className="rise" style={stagger(0)}>
        <p className={SECTION_LABEL}>Vacancies</p>
        <h1 className="mt-3 text-4xl font-semibold leading-[1.05] tracking-tighter text-zinc-900 md:text-5xl">
          Find the role that fits you
        </h1>
      </header>

      {matches.length > 0 && (
        <section className="rise mt-12" style={stagger(1)}>
          <p className={SECTION_LABEL}>Recommended for you</p>
          <ul className="mt-4 divide-y divide-zinc-200 border-y border-zinc-200">
            {matches.map((m, i) => (
              <VacancyRow
                key={m.job.id}
                job={m.job}
                index={i}
                extra={
                  m.matched_skills.length > 0 && (
                    <p className="mt-3 text-sm text-zinc-500">
                      Matches your skills:{' '}
                      <span className="font-medium text-zinc-900">{m.matched_skills.map((s) => s.name).join(', ')}</span>
                    </p>
                  )
                }
              />
            ))}
          </ul>
        </section>
      )}

      {/* Filters */}
      <form
        role="search"
        onSubmit={(e) => e.preventDefault()}
        className="rise mt-10 rounded-[2.5rem] border border-zinc-200/60 bg-white p-6 shadow-[0_20px_40px_-15px_rgba(24,24,27,0.08)] md:p-8"
        style={stagger(2)}
      >
        <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
          <label className="relative block">
            <span className="sr-only">Search title or company</span>
            <MagnifyingGlass size={18} weight="regular" className="pointer-events-none absolute left-5 top-1/2 -translate-y-1/2 text-zinc-500" />
            <input
              type="search"
              className={`${inputClass} pl-12`}
              placeholder="Search title or company"
              maxLength={100}
              value={form.q}
              onChange={(e) => setForm({ ...form, q: e.target.value })}
            />
          </label>
          <label className="relative block">
            <span className="sr-only">Location</span>
            <MapPin size={18} weight="regular" className="pointer-events-none absolute left-5 top-1/2 -translate-y-1/2 text-zinc-500" />
            <input
              className={`${inputClass} pl-12`}
              placeholder="Location, e.g. Surabaya"
              maxLength={100}
              value={form.location}
              onChange={(e) => setForm({ ...form, location: e.target.value })}
            />
          </label>
        </div>

        <div className="mt-8 grid gap-8 lg:grid-cols-2">
          <FilterGroup label="Type">
            <Chip selected={form.type === ''} onClick={() => setForm({ ...form, type: '' })}>
              All
            </Chip>
            {TYPES.map((t) => (
              <Chip key={t} selected={form.type === t} onClick={() => setForm({ ...form, type: t })}>
                {typeLabel(t)}
              </Chip>
            ))}
          </FilterGroup>
          <FilterGroup label="Work mode">
            <Chip selected={form.work_mode === ''} onClick={() => setForm({ ...form, work_mode: '' })}>
              All
            </Chip>
            {MODES.map((m) => (
              <Chip key={m} selected={form.work_mode === m} onClick={() => setForm({ ...form, work_mode: m })}>
                {modeLabel(m)}
              </Chip>
            ))}
          </FilterGroup>
        </div>

        {skills.length > 0 && (
          <div className="mt-8 border-t border-zinc-100 pt-8">
            <FilterGroup label={`Skills${form.skill.length ? ` (${form.skill.length}/${MAX_SKILLS})` : ''}`}>
              {visibleSkills.map((s) => (
                <Chip key={s.id} selected={form.skill.includes(s.id)} onClick={() => toggleSkill(s.id)}>
                  {s.name}
                </Chip>
              ))}
              {skills.length > SKILLS_COLLAPSED && (
                <button
                  type="button"
                  onClick={() => setShowAllSkills((v) => !v)}
                  className="px-3 py-2 text-sm font-medium text-zinc-900 underline-offset-4 hover:underline"
                >
                  {showAllSkills ? 'Show fewer' : `Show all ${skills.length}`}
                </button>
              )}
            </FilterGroup>
          </div>
        )}
      </form>

      {/* Results */}
      <section className="mt-10" aria-busy={loading}>
        <div className="flex items-center justify-between gap-4 pb-4">
          <p role="status" className="flex items-center gap-3 text-zinc-600">
            <SlidersHorizontal size={18} weight="regular" />
            <span className={jobs.length > 0 && !error ? 'font-mono text-sm' : ''}>{summary}</span>
          </p>
          {hasFilters && (
            <button
              type="button"
              onClick={() => setForm(EMPTY)}
              className="rounded-full px-4 py-2 text-sm font-medium text-zinc-900 transition-colors hover:bg-zinc-200/60 active:translate-y-[1px] active:scale-[0.98]"
            >
              Clear filters
            </button>
          )}
        </div>

        <div className="border-t border-zinc-200">
          {error && (
            <div role="alert" className="flex flex-col items-start gap-4 px-2 py-10">
              <p className="text-red-700">{error}</p>
              <button
                onClick={() => load(applied, null)}
                className="inline-flex min-h-11 items-center gap-2 rounded-full border border-zinc-200 bg-white px-5 text-sm font-medium text-zinc-900 transition duration-300 hover:border-zinc-300 active:translate-y-[1px] active:scale-[0.98]"
              >
                <ArrowClockwise size={16} weight="regular" />
                Reload
              </button>
            </div>
          )}

          {firstLoad && (
            <ul className="divide-y divide-zinc-200 border-b border-zinc-200">
              {[0, 1, 2, 3].map((i) => (
                <RowSkeleton key={i} />
              ))}
            </ul>
          )}

          {!error && !loading && jobs.length === 0 && (
            <div className="flex flex-col items-start gap-3 border-b border-zinc-200 px-2 py-12">
              <span className="grid h-12 w-12 place-items-center rounded-full bg-zinc-100 text-zinc-600">
                <MagnifyingGlass size={22} weight="regular" />
              </span>
              <p className="text-lg font-semibold tracking-tight text-zinc-900">No vacancies found</p>
              <p className="max-w-[46ch] text-sm leading-relaxed text-zinc-500">
                {hasFilters
                  ? 'Nothing matches these filters. Try a broader search or clear them to see every open role.'
                  : 'No alumnus has posted a role yet. Check back soon.'}
              </p>
              {hasFilters && (
                <button
                  onClick={() => setForm(EMPTY)}
                  className="mt-1 min-h-11 rounded-full bg-zinc-900 px-6 text-sm font-medium text-zinc-50 transition duration-300 hover:bg-zinc-800 active:translate-y-[1px] active:scale-[0.98]"
                >
                  Clear filters
                </button>
              )}
            </div>
          )}

          {jobs.length > 0 && (
            <ul
              className={`divide-y divide-zinc-200 border-b border-zinc-200 transition-opacity duration-300 ${loading && !loadingMore ? 'opacity-50' : ''
                }`}
            >
              {jobs.map((j, i) => (
                <VacancyRow key={j.id} job={j} index={i} />
              ))}
            </ul>
          )}
        </div>

        {!loading && !loadingMore && cursor && (
          <div className="mt-8 flex justify-center">
            <button
              onClick={() => load(applied, cursor)}
              className="min-h-12 rounded-full border border-zinc-200 bg-white px-8 text-sm font-medium text-zinc-900 transition duration-300 hover:border-zinc-300 active:translate-y-[1px] active:scale-[0.98]"
            >
              Show more
            </button>
          </div>
        )}
        {loadingMore && <p className="mt-8 text-center text-sm text-zinc-500">Loading more...</p>}
      </section>
    </div>
  );
}