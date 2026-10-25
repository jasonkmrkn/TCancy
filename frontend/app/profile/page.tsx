'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import FormField, { inputClass } from '@/components/FormField';
import { api, ApiError } from '@/lib/api';
import { useAuth } from '@/lib/auth';

type Skill = { id: string; name: string };

type ApplicantProfile = {
  role: 'applicant';
  full_name: string;
  email: string;
  phone: string;
  nik: string;
  address: string;
  birth_date: string;
  angkatan: number;
  skills: Skill[];
  preferred_type: string | null;
  preferred_location: string | null;
};

type AlumniProfile = {
  role: 'alumni';
  full_name: string | null;
  company: string | null;
  angkatan: number | null;
  verification: { state: string; reason: string | null };
};

type Profile = ApplicantProfile | AlumniProfile;

const TYPES = [
  { value: '', label: 'No preference' },
  { value: 'internship', label: 'Internship' },
  { value: 'fulltime', label: 'Full-time' },
  { value: 'parttime', label: 'Part-time' },
  { value: 'contract', label: 'Contract' },
];

type Form = {
  full_name: string;
  email: string;
  phone: string;
  nik: string;
  address: string;
  birth_date: string;
  angkatan: string;
  preferred_type: string;
  preferred_location: string;
  company: string;
};

function toForm(p: Profile): Form {
  if (p.role === 'applicant') {
    return {
      full_name: p.full_name,
      email: p.email,
      phone: p.phone,
      nik: p.nik,
      address: p.address,
      birth_date: p.birth_date,
      angkatan: String(p.angkatan),
      preferred_type: p.preferred_type ?? '',
      preferred_location: p.preferred_location ?? '',
      company: '',
    };
  }
  return {
    full_name: p.full_name ?? '',
    email: '',
    phone: '',
    nik: '',
    address: '',
    birth_date: '',
    angkatan: p.angkatan ? String(p.angkatan) : '',
    preferred_type: '',
    preferred_location: '',
    company: p.company ?? '',
  };
}

function mapFields(err: ApiError): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, msg] of Object.entries(err.fields)) {
    const name = key.split('.')[0];
    if (name && !(name in out)) out[name] = msg;
  }
  if (err.code === 'EMAIL_TAKEN') out.email = err.message;
  if (err.code === 'NIK_TAKEN') out.nik = err.message;
  return out;
}

export default function ProfilePage() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [skillIds, setSkillIds] = useState<string[]>([]);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [password, setPassword] = useState('');
  const [deleteError, setDeleteError] = useState('');

  const allowed = !!user && (user.role === 'applicant' || user.role === 'alumni');

  useEffect(() => {
    if (!allowed) return;
    api<Profile>('/me/profile')
      .then((p) => {
        setProfile(p);
        setForm(toForm(p));
        if (p.role === 'applicant') setSkillIds(p.skills.map((s) => s.id));
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load the profile.'));
  }, [allowed]);

  useEffect(() => {
    if (user?.role !== 'applicant') return;
    api<Skill[]>('/skills')
      .then(setSkills)
      .catch(() => setError('Could not load the skill list.'));
  }, [user?.role]);

  function set(name: keyof Form) {
    return (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
      setSaved(false);
      setForm((f) => (f ? { ...f, [name]: e.target.value } : f));
    };
  }

  function toggleSkill(id: string) {
    setSaved(false);
    setSkillIds((cur) => (cur.includes(id) ? cur.filter((s) => s !== id) : [...cur, id]));
  }

  function validate(f: Form, role: string): Record<string, string> {
    const out: Record<string, string> = {};
    const thisYear = new Date().getFullYear();
    const year = Number(f.angkatan);
    if (f.full_name.trim().length > 200) out.full_name = 'Full name must be at most 200 characters.';
    if (role === 'alumni') {
      if (f.company.trim().length > 200) out.company = 'Company must be at most 200 characters.';
      if (f.angkatan && (!Number.isInteger(year) || year < 1990 || year > thisYear)) {
        out.angkatan = 'Class year must be between 1990 and ' + thisYear + '.';
      }
      return out;
    }
    if (!f.full_name.trim()) out.full_name = 'Full name is required.';
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(f.email) || f.email.length > 254) out.email = 'Enter a valid email address.';
    if (!/^\+?\d{8,15}$/.test(f.phone)) out.phone = 'Phone must be 8-15 digits, optionally starting with +.';
    if (!/^\d{16}$/.test(f.nik)) out.nik = 'National ID number must be exactly 16 digits.';
    if (!f.address.trim()) out.address = 'Address is required.';
    else if (f.address.trim().length > 500) out.address = 'Address must be at most 500 characters.';
    if (!f.birth_date) out.birth_date = 'Birth date is required.';
    if (!Number.isInteger(year) || year < 1990 || year > thisYear) {
      out.angkatan = 'Class year must be between 1990 and ' + thisYear + '.';
    }
    if (skillIds.length < 1 || skillIds.length > 30) out.skill_ids = 'Pick 1 to 30 skills.';
    if (f.preferred_location.length > 100) out.preferred_location = 'Preferred location must be at most 100 characters.';
    return out;
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!form || !profile) return;
    setError('');
    setSaved(false);
    const problems = validate(form, profile.role);
    setFields(problems);
    if (Object.keys(problems).length > 0) return;
    const body =
      profile.role === 'applicant'
        ? {
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
          }
        : {
            full_name: form.full_name.trim() || null,
            company: form.company.trim() || null,
            angkatan: form.angkatan ? Number(form.angkatan) : null,
          };
    setBusy(true);
    try {
      await api('/me/profile', { method: 'PUT', body });
      const fresh = await api<Profile>('/me/profile');
      setProfile(fresh);
      setForm(toForm(fresh));
      if (fresh.role === 'applicant') setSkillIds(fresh.skills.map((s) => s.id));
      setSaved(true);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        setFields(mapFields(err));
      } else {
        setError('Something went wrong.');
      }
    } finally {
      setBusy(false);
    }
  }

  async function deleteAccount(e: React.FormEvent) {
    e.preventDefault();
    setDeleteError('');
    if (!password) {
      setDeleteError('Enter your password to confirm.');
      return;
    }
    if (!window.confirm('Delete your account permanently? This cannot be undone.')) return;
    setBusy(true);
    try {
      await api('/me/account', { method: 'DELETE', body: { password } });
      await logout().catch(() => undefined);
      router.push('/');
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.message : 'Something went wrong.');
      setBusy(false);
    }
  }

  if (loading) return <p className="text-sm text-gray-600">Checking session...</p>;

  if (!user) {
    return (
      <div className="text-sm">
        <h1 className="text-2xl font-bold">Profile</h1>
        <p className="mt-4">
          Please{' '}
          <Link className="underline" href="/login">
            sign in
          </Link>{' '}
          to see your profile.
        </p>
      </div>
    );
  }

  if (!allowed) {
    return (
      <div className="text-sm">
        <h1 className="text-2xl font-bold">Profile</h1>
        <p className="mt-4">Admin accounts do not have a profile.</p>
      </div>
    );
  }

  return (
    <div className="max-w-xl">
      <h1 className="text-2xl font-bold">Profile</h1>
      <p className="mt-1 text-sm text-gray-600">
        Signed in as <strong>{user.username}</strong> ({user.role}, {user.status}).
      </p>

      {profile?.role === 'alumni' && (
        <p className="mt-3 rounded border p-2 text-sm">
          Verification: <strong>{profile.verification.state}</strong>
          {profile.verification.reason && <> - {profile.verification.reason}</>}
          {profile.verification.state !== 'approved' && (
            <span className="block text-gray-600">Full name, company and class year are required before approval.</span>
          )}
        </p>
      )}

      {!form && !error && <p className="mt-4 text-sm text-gray-600">Loading profile...</p>}

      {form && profile && (
        <form onSubmit={save} className="mt-4 flex flex-col gap-3" noValidate>
          <FormField label="Full name" error={fields.full_name}>
            <input className={inputClass} value={form.full_name} onChange={set('full_name')} />
          </FormField>
          {profile.role === 'alumni' && (
            <FormField label="Company" error={fields.company}>
              <input className={inputClass} value={form.company} onChange={set('company')} />
            </FormField>
          )}
          {profile.role === 'applicant' && (
            <>
              <FormField label="Email" error={fields.email}>
                <input className={inputClass} type="email" value={form.email} onChange={set('email')} />
              </FormField>
              <FormField label="Phone" error={fields.phone}>
                <input className={inputClass} value={form.phone} onChange={set('phone')} />
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
            </>
          )}
          <FormField label="Class year (angkatan)" error={fields.angkatan}>
            <input className={inputClass} inputMode="numeric" value={form.angkatan} onChange={set('angkatan')} />
          </FormField>
          {profile.role === 'applicant' && (
            <>
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
          {saved && <p className="text-sm text-green-700">Profile saved.</p>}
          <button className="rounded border px-3 py-1 text-sm" type="submit" disabled={busy}>
            {busy ? 'Saving...' : 'Save profile'}
          </button>
        </form>
      )}
      {!form && error && <p className="mt-4 text-sm text-red-700">{error}</p>}

      <section className="mt-10 border-t pt-4">
        <h2 className="text-lg font-semibold">Delete account</h2>
        <p className="mt-1 text-sm text-gray-600">
          This removes your account, profile, applications, testimonials and uploaded files.
        </p>
        {!deleting ? (
          <button className="mt-3 rounded border px-3 py-1 text-sm text-red-700" type="button" onClick={() => setDeleting(true)}>
            Delete my account
          </button>
        ) : (
          <form onSubmit={deleteAccount} className="mt-3 flex max-w-sm flex-col gap-3">
            <FormField label="Confirm with your password" error={deleteError}>
              <input
                className={inputClass}
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
            </FormField>
            <div className="flex gap-2">
              <button className="rounded border px-3 py-1 text-sm text-red-700" type="submit" disabled={busy}>
                Delete permanently
              </button>
              <button
                className="rounded border px-3 py-1 text-sm"
                type="button"
                onClick={() => {
                  setDeleting(false);
                  setPassword('');
                  setDeleteError('');
                }}
              >
                Cancel
              </button>
            </div>
          </form>
        )}
      </section>
    </div>
  );
}
