'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import { MapPin } from '@phosphor-icons/react';
import { stagger } from '@/components/AuthShell';
import Chip from '@/components/Chip';
import FormField, { FormAlert, inputClass, textareaClass } from '@/components/FormField';
import { SECTION_LABEL } from '@/components/home/Band';
import { BTN_OUTLINE, BTN_PRIMARY, CARD, Pill } from '@/components/ui';
import { api, ApiError } from '@/lib/api';
import { modeLabel, typeLabel } from '@/lib/labels';

type Skill = { id: string; name: string };

export type JobValues = {
  title: string;
  company: string;
  type: string;
  work_mode: string;
  location: string;
  description: string;
  requirements: string;
  deadline: string;
  skill_ids: string[];
};

export const emptyJob: JobValues = {
  title: '',
  company: '',
  type: 'internship',
  work_mode: 'onsite',
  location: '',
  description: '',
  requirements: '',
  deadline: '',
  skill_ids: [],
};

const TYPES = [
  { value: 'internship', label: 'Internship' },
  { value: 'fulltime', label: 'Full-time' },
  { value: 'parttime', label: 'Part-time' },
  { value: 'contract', label: 'Contract' },
];

const MODES = [
  { value: 'onsite', label: 'On-site' },
  { value: 'hybrid', label: 'Hybrid' },
  { value: 'remote', label: 'Remote' },
];

function validate(v: JobValues, isNew: boolean): Record<string, string> {
  const e: Record<string, string> = {};
  if (!v.title.trim()) e.title = 'Title is required.';
  else if (v.title.length > 200) e.title = 'Title can have at most 200 characters.';
  if (!v.company.trim()) e.company = 'Company is required.';
  else if (v.company.length > 200) e.company = 'Company can have at most 200 characters.';
  if (v.location.length > 200) e.location = 'Location can have at most 200 characters.';
  if (!v.description.trim()) e.description = 'Description is required.';
  else if (v.description.length > 10000) e.description = 'Description can have at most 10000 characters.';
  if (v.requirements.length > 10000) e.requirements = 'Requirements can have at most 10000 characters.';
  if (isNew && v.deadline && v.deadline < new Date().toISOString().slice(0, 10)) {
    e.deadline = 'Deadline cannot be in the past.';
  }
  if (v.skill_ids.length > 20) e.skill_ids = 'Choose at most 20 skills.';
  return e;
}

function formatDeadline(value: string): string {
  return new Date(value + 'T00:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

function Counter({ value, max }: { value: string; max: number }) {
  return (
    <span className={`font-mono text-xs ${value.length > max ? 'text-red-700' : 'text-zinc-400'}`}>
      {value.length}/{max}
    </span>
  );
}

export default function JobForm({ jobId, initial }: { jobId?: string; initial: JobValues }) {
  const router = useRouter();
  const [values, setValues] = useState<JobValues>(initial);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [skillsState, setSkillsState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState('');
  const [busy, setBusy] = useState(false);

  const loadSkills = useCallback(() => {
    setSkillsState('loading');
    api<Skill[]>('/skills')
      .then((s) => {
        setSkills(s);
        setSkillsState('ready');
      })
      .catch(() => setSkillsState('error'));
  }, []);

  useEffect(loadSkills, [loadSkills]);

  function set<K extends keyof JobValues>(key: K, value: JobValues[K]) {
    setValues((v) => ({ ...v, [key]: value }));
  }

  function toggleSkill(id: string) {
    set(
      'skill_ids',
      values.skill_ids.includes(id) ? values.skill_ids.filter((s) => s !== id) : [...values.skill_ids, id],
    );
  }

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    setFormError('');
    const found = validate(values, !jobId);
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    setBusy(true);
    const body = {
      title: values.title.trim(),
      company: values.company.trim(),
      type: values.type,
      work_mode: values.work_mode,
      location: values.location.trim() || null,
      description: values.description,
      requirements: values.requirements || null,
      deadline: values.deadline || null,
      skill_ids: values.skill_ids,
    };
    try {
      const saved = jobId
        ? await api<{ id: string }>(`/jobs/${jobId}`, { method: 'PUT', body })
        : await api<{ id: string }>('/jobs', { method: 'POST', body });
      router.push(`/vacancy/${saved.id}`);
    } catch (e) {
      if (e instanceof ApiError) {
        setErrors(e.fields);
        setFormError(e.message);
      } else {
        setFormError('Could not save the vacancy.');
      }
      setBusy(false);
    }
  }

  const chosen = skills.filter((s) => values.skill_ids.includes(s.id));

  return (
    <div className="mt-10 grid items-start gap-6 lg:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]">
      <form onSubmit={submit} noValidate className={`rise flex flex-col gap-10 ${CARD}`} style={stagger(1)}>
        {/* Basics */}
        <section className="flex flex-col gap-5">
          <h2 className={SECTION_LABEL}>The role</h2>
          <FormField label="Title" error={errors.title}>
            <input
              className={inputClass}
              value={values.title}
              onChange={(e) => set('title', e.target.value)}
              placeholder="Backend Engineer Intern"
            />
          </FormField>
          <div className="grid gap-5 sm:grid-cols-2">
            <FormField label="Company" error={errors.company}>
              <input className={inputClass} value={values.company} onChange={(e) => set('company', e.target.value)} />
            </FormField>
            <FormField label="Location" error={errors.location} hint="Optional.">
              <input
                className={inputClass}
                value={values.location}
                onChange={(e) => set('location', e.target.value)}
                placeholder="Surabaya"
              />
            </FormField>
          </div>

          <fieldset className="flex flex-col gap-2 text-sm">
            <legend className="mb-2 font-medium text-zinc-900">Type</legend>
            <div role="group" className="flex flex-wrap gap-2">
              {TYPES.map((t) => (
                <Chip key={t.value} selected={values.type === t.value} onClick={() => set('type', t.value)}>
                  {t.label}
                </Chip>
              ))}
            </div>
            {errors.type && (
              <p role="alert" className="text-[13px] text-red-700">
                {errors.type}
              </p>
            )}
          </fieldset>

          <fieldset className="flex flex-col gap-2 text-sm">
            <legend className="mb-2 font-medium text-zinc-900">Work mode</legend>
            <div role="group" className="flex flex-wrap gap-2">
              {MODES.map((m) => (
                <Chip key={m.value} selected={values.work_mode === m.value} onClick={() => set('work_mode', m.value)}>
                  {m.label}
                </Chip>
              ))}
            </div>
            {errors.work_mode && (
              <p role="alert" className="text-[13px] text-red-700">
                {errors.work_mode}
              </p>
            )}
          </fieldset>
        </section>

        {/* Details */}
        <section className="flex flex-col gap-5">
          <h2 className={SECTION_LABEL}>Details</h2>
          <div className="flex flex-col gap-2">
            <FormField label="Description" error={errors.description}>
              <textarea
                className={textareaClass}
                rows={7}
                value={values.description}
                onChange={(e) => set('description', e.target.value)}
                placeholder="What will they work on? What does a normal week look like?"
              />
            </FormField>
            <div className="-mt-1 flex justify-end">
              <Counter value={values.description} max={10000} />
            </div>
          </div>
          <div className="flex flex-col gap-2">
            <FormField label="Requirements" error={errors.requirements} hint="Optional.">
              <textarea
                className={textareaClass}
                rows={4}
                value={values.requirements}
                onChange={(e) => set('requirements', e.target.value)}
              />
            </FormField>
            <div className="-mt-1 flex justify-end">
              <Counter value={values.requirements} max={10000} />
            </div>
          </div>
        </section>

        {/* Matching */}
        <section className="flex flex-col gap-5">
          <h2 className={SECTION_LABEL}>Matching</h2>

          <fieldset className="flex flex-col gap-2 text-sm" data-invalid={errors.skill_ids ? 'true' : undefined}>
            <div className="flex items-baseline justify-between">
              <legend className="font-medium text-zinc-900">Skills</legend>
              <span className="font-mono text-xs text-zinc-500">{values.skill_ids.length}/20</span>
            </div>
            {skillsState === 'loading' && (
              <div aria-hidden className="flex animate-pulse flex-wrap gap-2">
                {[84, 64, 96, 72, 88, 60, 76].map((w, i) => (
                  <div key={i} className="h-9 rounded-full bg-zinc-200/70" style={{ width: w }} />
                ))}
              </div>
            )}
            {skillsState === 'error' && (
              <p className="flex items-center gap-2 text-zinc-600">
                The skill list is unavailable right now.
                <button type="button" onClick={loadSkills} className="font-medium text-zinc-900 underline-offset-4 hover:underline">
                  Try again
                </button>
              </p>
            )}
            {skillsState === 'ready' && (
              <div className="flex flex-wrap gap-2">
                {skills.map((s) => (
                  <Chip key={s.id} selected={values.skill_ids.includes(s.id)} onClick={() => toggleSkill(s.id)}>
                    {s.name}
                  </Chip>
                ))}
              </div>
            )}
            {errors.skill_ids ? (
              <p role="alert" className="text-[13px] text-red-700">
                {errors.skill_ids}
              </p>
            ) : (
              <p className="text-[13px] text-zinc-500">Applicants with these skills see your vacancy in their recommendations.</p>
            )}
          </fieldset>

          <div className="sm:max-w-xs">
            <FormField label="Deadline" error={errors.deadline} hint="Optional. Applications close after this date.">
              <input type="date" className={inputClass} value={values.deadline} onChange={(e) => set('deadline', e.target.value)} />
            </FormField>
          </div>
        </section>

        {formError && <FormAlert>{formError}</FormAlert>}

        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" disabled={busy} className={BTN_PRIMARY}>
            {busy ? 'Saving...' : jobId ? 'Save changes' : 'Create vacancy'}
          </button>
          <Link href="/jobs" className={BTN_OUTLINE}>
            Cancel
          </Link>
        </div>
      </form>

      {/* Live preview */}
      <aside className="rise lg:sticky lg:top-24" style={stagger(2)} aria-label="Preview">
        <section className="rounded-[2.5rem] border border-zinc-200/60 bg-white p-8 shadow-[0_20px_40px_-15px_rgba(24,24,27,0.08)]">
          <h2 className={SECTION_LABEL}>How students will see it</h2>
          <div className="mt-6">
            <p className="text-xl font-semibold tracking-tight text-zinc-900">
              {values.title.trim() || <span className="text-zinc-300">Vacancy title</span>}
            </p>
            <p className="mt-1.5 text-sm text-zinc-500">
              {values.company.trim() || <span className="text-zinc-300">Company</span>}
              <span aria-hidden> · </span>
              {typeLabel(values.type)}
              <span aria-hidden> · </span>
              {modeLabel(values.work_mode)}
              {values.location.trim() && (
                <span className="ml-3 inline-flex items-center gap-1">
                  <MapPin size={14} />
                  {values.location.trim()}
                </span>
              )}
            </p>
            {values.description.trim() && (
              <p className="mt-4 line-clamp-3 text-sm leading-relaxed text-zinc-600">{values.description.trim()}</p>
            )}
            {chosen.length > 0 && (
              <ul className="mt-4 flex flex-wrap gap-2" aria-label="Skills">
                {chosen.map((s) => (
                  <li key={s.id} className="rounded-full bg-zinc-100 px-3 py-1 text-xs text-zinc-700">
                    {s.name}
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-5 flex items-center gap-2 border-t border-zinc-200 pt-4 font-mono text-xs text-zinc-500">
              <Pill tone="solid">Open</Pill>
              {values.deadline ? `Deadline ${formatDeadline(values.deadline)}` : 'No deadline'}
            </p>
          </div>
        </section>
      </aside>
    </div>
  );
}