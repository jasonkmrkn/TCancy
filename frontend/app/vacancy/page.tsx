'use client';

import { useCallback, useEffect, useState } from 'react';
import JobCard, { Job } from '@/components/JobCard';
import { api, ApiError } from '@/lib/api';
import { useAuth } from '@/lib/auth';

type Skill = { id: string; name: string };
type Match = { job: Job; score: number; matched_skills: Skill[] };

type Filters = { q: string; location: string; type: string; work_mode: string; skill: string[] };
const EMPTY: Filters = { q: '', location: '', type: '', work_mode: '', skill: [] };

const TYPES = ['internship', 'fulltime', 'parttime', 'contract'];
const MODES = ['onsite', 'hybrid', 'remote'];

export default function VacancyPage() {
  const { user } = useAuth();
  const [form, setForm] = useState<Filters>(EMPTY);
  const [applied, setApplied] = useState<Filters>(EMPTY);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [matches, setMatches] = useState<Match[]>([]);

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
    setLoading(true);
    setError('');
    try {
      const r = await api<{ items: Job[]; next_cursor: string | null }>('/jobs', {
        query: { ...f, limit: 20, cursor: after },
      });
      setJobs((prev) => (after ? [...prev, ...r.items] : r.items));
      setCursor(r.next_cursor);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load vacancies.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(applied, null);
  }, [applied, load]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setApplied({ ...form, q: form.q.trim(), location: form.location.trim() });
  }

  function reset() {
    setForm(EMPTY);
    setApplied(EMPTY);
  }

  function toggleSkill(id: string) {
    setForm((f) => {
      if (f.skill.includes(id)) return { ...f, skill: f.skill.filter((s) => s !== id) };
      if (f.skill.length >= 20) return f;
      return { ...f, skill: [...f.skill, id] };
    });
  }

  const input = 'w-full rounded border px-2 py-1 text-sm';

  return (
    <div>
      <h1 className="text-2xl font-semibold">Vacancies</h1>

      {matches.length > 0 && (
        <section className="mt-4">
          <h2 className="text-lg font-semibold">Recommended for you</h2>
          <ul className="mt-2 divide-y rounded border">
            {matches.map((m) => (
              <JobCard
                key={m.job.id}
                job={m.job}
                extra={<p className="text-green-700">Matches: {m.matched_skills.map((s) => s.name).join(', ')}</p>}
              />
            ))}
          </ul>
        </section>
      )}

      <form onSubmit={submit} className="mt-4 space-y-3 rounded border p-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-sm">
            Search
            <input
              className={input}
              maxLength={100}
              value={form.q}
              onChange={(e) => setForm({ ...form, q: e.target.value })}
            />
          </label>
          <label className="text-sm">
            Location
            <input
              className={input}
              maxLength={100}
              value={form.location}
              onChange={(e) => setForm({ ...form, location: e.target.value })}
            />
          </label>
          <label className="text-sm">
            Type
            <select className={input} value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
              <option value="">All</option>
              {TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            Work mode
            <select
              className={input}
              value={form.work_mode}
              onChange={(e) => setForm({ ...form, work_mode: e.target.value })}
            >
              <option value="">All</option>
              {MODES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
        </div>
        {skills.length > 0 && (
          <fieldset>
            <legend className="text-sm">Skills</legend>
            <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
              {skills.map((s) => (
                <label key={s.id} className="text-sm">
                  <input
                    type="checkbox"
                    className="mr-1"
                    checked={form.skill.includes(s.id)}
                    onChange={() => toggleSkill(s.id)}
                  />
                  {s.name}
                </label>
              ))}
            </div>
          </fieldset>
        )}
        <div className="flex gap-2">
          <button type="submit" className="rounded border bg-gray-900 px-3 py-1 text-sm text-white">
            Apply filters
          </button>
          <button type="button" onClick={reset} className="rounded border px-3 py-1 text-sm">
            Reset
          </button>
        </div>
      </form>

      {error && <p className="mt-3 text-sm text-red-700">{error}</p>}
      {!error && !loading && jobs.length === 0 && <p className="mt-3 text-sm text-gray-600">No vacancies found.</p>}
      {jobs.length > 0 && (
        <ul className="mt-4 divide-y rounded border">
          {jobs.map((j) => (
            <JobCard key={j.id} job={j} />
          ))}
        </ul>
      )}
      {loading && <p className="mt-3 text-sm text-gray-600">Loading...</p>}
      {!loading && cursor && (
        <button onClick={() => load(applied, cursor)} className="mt-3 rounded border px-3 py-1 text-sm">
          Show more
        </button>
      )}
    </div>
  );
}
