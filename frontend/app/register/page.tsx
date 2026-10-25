'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import FormField, { inputClass } from '@/components/FormField';
import { api, ApiError } from '@/lib/api';
import { useAuth } from '@/lib/auth';

type Skill = { id: string; name: string };
type Kind = 'applicant' | 'alumni';

const TYPES = [
  { value: '', label: 'No preference' },
  { value: 'internship', label: 'Internship' },
  { value: 'fulltime', label: 'Full-time' },
  { value: 'parttime', label: 'Part-time' },
  { value: 'contract', label: 'Contract' },
];

const EMPTY = {
  username: '',
  password: '',
  confirm: '',
  full_name: '',
  email: '',
  phone: '',
  nik: '',
  address: '',
  birth_date: '',
  angkatan: '',
  preferred_type: '',
  preferred_location: '',
};

// Server field paths look like "profile.email" or "profile.skill_ids.3"; the form uses flat names.
function mapFields(err: ApiError): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, msg] of Object.entries(err.fields)) {
    const parts = key.split('.');
    const name = parts[0] === 'profile' ? parts[1] : parts[0];
    if (name && !(name in out)) out[name] = msg;
  }
  if (err.code === 'USERNAME_TAKEN') out.username = err.message;
  if (err.code === 'EMAIL_TAKEN') out.email = err.message;
  if (err.code === 'NIK_TAKEN') out.nik = err.message;
  return out;
}

export default function RegisterPage() {
  const { user, loading, login } = useAuth();
  const router = useRouter();
  const [kind, setKind] = useState<Kind>('applicant');
  const [form, setForm] = useState(EMPTY);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [skillIds, setSkillIds] = useState<string[]>([]);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<Skill[]>('/skills')
      .then(setSkills)
      .catch(() => setError('Could not load the skill list.'));
  }, []);

  function set(name: keyof typeof EMPTY) {
    return (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
      setForm((f) => ({ ...f, [name]: e.target.value }));
  }

  function toggleSkill(id: string) {
    setSkillIds((cur) => (cur.includes(id) ? cur.filter((s) => s !== id) : [...cur, id]));
  }

  function validate(): Record<string, string> {
    const out: Record<string, string> = {};
    const username = form.username.trim();
    if (username.length < 3 || username.length > 64) out.username = 'Username must be 3-64 characters.';
    if (form.password.length < 8 || form.password.length > 256) out.password = 'Password must be 8-256 characters.';
    if (form.confirm !== form.password) out.confirm = 'Passwords do not match.';
    if (kind === 'applicant') {
      const thisYear = new Date().getFullYear();
      if (!form.full_name.trim()) out.full_name = 'Full name is required.';
      else if (form.full_name.trim().length > 200) out.full_name = 'Full name must be at most 200 characters.';
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email) || form.email.length > 254) out.email = 'Enter a valid email address.';
      if (!/^\+?\d{8,15}$/.test(form.phone)) out.phone = 'Phone must be 8-15 digits, optionally starting with +.';
      if (!/^\d{16}$/.test(form.nik)) out.nik = 'National ID number must be exactly 16 digits.';
      if (!form.address.trim()) out.address = 'Address is required.';
      else if (form.address.trim().length > 500) out.address = 'Address must be at most 500 characters.';
      if (!form.birth_date) out.birth_date = 'Birth date is required.';
      const year = Number(form.angkatan);
      if (!Number.isInteger(year) || year < 1990 || year > thisYear) {
        out.angkatan = 'Class year must be between 1990 and ' + thisYear + '.';
      }
      if (skillIds.length < 1 || skillIds.length > 30) out.skill_ids = 'Pick 1 to 30 skills.';
      if (form.preferred_location.length > 100) out.preferred_location = 'Preferred location must be at most 100 characters.';
    }
    return out;
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    const problems = validate();
    setFields(problems);
    if (Object.keys(problems).length > 0) return;
    setBusy(true);
    const username = form.username.trim().toLowerCase();
    try {
      if (kind === 'alumni') {
        await api('/auth/register/alumni', { method: 'POST', body: { username, password: form.password } });
      } else {
        await api('/auth/register', {
          method: 'POST',
          body: {
            username,
            password: form.password,
            profile: {
              full_name: form.full_name.trim(),
              email: form.email.trim(),
              phone: form.phone,
              nik: form.nik,
              address: form.address.trim(),
              birth_date: form.birth_date,
              angkatan: Number(form.angkatan),
              skill_ids: skillIds,
              preferred_type: form.preferred_type || null,
              preferred_location: form.preferred_location.trim() || null,
            },
          },
        });
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        setFields(mapFields(err));
      } else {
        setError('Something went wrong.');
      }
      setBusy(false);
      return;
    }
    try {
      await login(username, form.password);
      router.push('/');
    } catch {
      router.push('/login');
    }
  }

  if (loading) return <p className="text-sm text-gray-600">Checking session...</p>;

  if (user) {
    return (
      <div className="max-w-sm text-sm">
        <h1 className="text-2xl font-bold">Register</h1>
        <p className="mt-4">
          You are already signed in as <strong>{user.username}</strong>. Sign out first to create another account.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-xl">
      <h1 className="text-2xl font-bold">Register</h1>
      <div className="mt-4 flex gap-2 text-sm">
        {(['applicant', 'alumni'] as Kind[]).map((k) => (
          <button
            key={k}
            type="button"
            onClick={() => {
              setKind(k);
              setFields({});
              setError('');
            }}
            className={kind === k ? 'rounded border bg-gray-200 px-3 py-1 font-medium' : 'rounded border px-3 py-1'}
          >
            {k === 'applicant' ? 'Applicant' : 'Alumni'}
          </button>
        ))}
      </div>
      {kind === 'alumni' && (
        <p className="mt-3 text-sm text-gray-600">
          Alumni accounts stay pending until an admin approves them. After signing in, complete your profile.
        </p>
      )}
      <form onSubmit={submit} className="mt-4 flex flex-col gap-3" noValidate>
        <FormField label="Username" error={fields.username}>
          <input className={inputClass} value={form.username} onChange={set('username')} autoComplete="username" />
        </FormField>
        <FormField label="Password" error={fields.password}>
          <input className={inputClass} type="password" value={form.password} onChange={set('password')} autoComplete="new-password" />
        </FormField>
        <FormField label="Confirm password" error={fields.confirm}>
          <input className={inputClass} type="password" value={form.confirm} onChange={set('confirm')} autoComplete="new-password" />
        </FormField>

        {kind === 'applicant' && (
          <>
            <FormField label="Full name" error={fields.full_name}>
              <input className={inputClass} value={form.full_name} onChange={set('full_name')} />
            </FormField>
            <FormField label="Email" error={fields.email}>
              <input className={inputClass} type="email" value={form.email} onChange={set('email')} />
            </FormField>
            <FormField label="Phone" error={fields.phone}>
              <input className={inputClass} value={form.phone} onChange={set('phone')} placeholder="+6281234567890" />
            </FormField>
            <FormField label="National ID number (16 digits)" error={fields.nik}>
              <input className={inputClass} value={form.nik} onChange={set('nik')} inputMode="numeric" />
            </FormField>
            <FormField label="Address" error={fields.address}>
              <textarea className={inputClass} rows={3} value={form.address} onChange={set('address')} />
            </FormField>
            <FormField label="Birth date" error={fields.birth_date}>
              <input className={inputClass} type="date" value={form.birth_date} onChange={set('birth_date')} />
            </FormField>
            <FormField label="Class year (angkatan)" error={fields.angkatan}>
              <input className={inputClass} inputMode="numeric" value={form.angkatan} onChange={set('angkatan')} />
            </FormField>
            <fieldset className="text-sm">
              <legend className="mb-1 font-medium">Skills</legend>
              <div className="grid grid-cols-2 gap-1 sm:grid-cols-3">
                {skills.map((s) => (
                  <label key={s.id} className="flex items-center gap-1">
                    <input type="checkbox" checked={skillIds.includes(s.id)} onChange={() => toggleSkill(s.id)} />
                    {s.name}
                  </label>
                ))}
              </div>
              {fields.skill_ids && <p className="mt-1 text-red-700">{fields.skill_ids}</p>}
            </fieldset>
            <FormField label="Preferred job type (optional)" error={fields.preferred_type}>
              <select className={inputClass} value={form.preferred_type} onChange={set('preferred_type')}>
                {TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </FormField>
            <FormField label="Preferred location (optional)" error={fields.preferred_location}>
              <input className={inputClass} value={form.preferred_location} onChange={set('preferred_location')} />
            </FormField>
          </>
        )}

        {error && <p className="text-sm text-red-700">{error}</p>}
        <button className="rounded border px-3 py-1 text-sm" type="submit" disabled={busy}>
          {busy ? 'Creating account...' : 'Create account'}
        </button>
      </form>
      <p className="mt-4 text-sm text-gray-600">
        Already have an account?{' '}
        <Link className="underline" href="/login">
          Sign in
        </Link>
      </p>
    </div>
  );
}
