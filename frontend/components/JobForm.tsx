'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import FormField, { inputClass } from '@/components/FormField';
import { api, ApiError } from '@/lib/api';

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

export default function JobForm({ jobId, initial }: { jobId?: string; initial: JobValues }) {
  const router = useRouter();
  const [values, setValues] = useState<JobValues>(initial);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<Skill[]>('/skills')
      .then(setSkills)
      .catch(() => setFormError('Could not load the skill list.'));
  }, []);

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

  return (
    <form onSubmit={submit} className="mt-4 max-w-xl space-y-3">
      <FormField label="Title" error={errors.title}>
        <input className={inputClass} value={values.title} onChange={(e) => set('title', e.target.value)} />
      </FormField>
      <FormField label="Company" error={errors.company}>
        <input className={inputClass} value={values.company} onChange={(e) => set('company', e.target.value)} />
      </FormField>
      <FormField label="Type" error={errors.type}>
        <select className={inputClass} value={values.type} onChange={(e) => set('type', e.target.value)}>
          <option value="internship">Internship</option>
          <option value="fulltime">Full time</option>
          <option value="parttime">Part time</option>
          <option value="contract">Contract</option>
        </select>
      </FormField>
      <FormField label="Work mode" error={errors.work_mode}>
        <select className={inputClass} value={values.work_mode} onChange={(e) => set('work_mode', e.target.value)}>
          <option value="onsite">On site</option>
          <option value="hybrid">Hybrid</option>
          <option value="remote">Remote</option>
        </select>
      </FormField>
      <FormField label="Location (optional)" error={errors.location}>
        <input className={inputClass} value={values.location} onChange={(e) => set('location', e.target.value)} />
      </FormField>
      <FormField label="Description" error={errors.description}>
        <textarea
          className={inputClass}
          rows={6}
          value={values.description}
          onChange={(e) => set('description', e.target.value)}
        />
      </FormField>
      <FormField label="Requirements (optional)" error={errors.requirements}>
        <textarea
          className={inputClass}
          rows={4}
          value={values.requirements}
          onChange={(e) => set('requirements', e.target.value)}
        />
      </FormField>
      <FormField label="Deadline (optional)" error={errors.deadline}>
        <input
          type="date"
          className={inputClass}
          value={values.deadline}
          onChange={(e) => set('deadline', e.target.value)}
        />
      </FormField>
      <fieldset className="text-sm">
        <legend className="mb-1 font-medium">Skills (up to 20)</legend>
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {skills.map((s) => (
            <label key={s.id} className="flex items-center gap-1">
              <input type="checkbox" checked={values.skill_ids.includes(s.id)} onChange={() => toggleSkill(s.id)} />
              {s.name}
            </label>
          ))}
        </div>
        {errors.skill_ids && <p className="mt-1 text-red-700">{errors.skill_ids}</p>}
      </fieldset>
      {formError && <p className="text-sm text-red-700">{formError}</p>}
      <button type="submit" disabled={busy} className="rounded border px-3 py-1 text-sm disabled:opacity-50">
        {busy ? 'Saving...' : jobId ? 'Save changes' : 'Create vacancy'}
      </button>
    </form>
  );
}
