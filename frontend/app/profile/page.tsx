'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import { CheckCircle, ShieldCheck, Warning } from '@phosphor-icons/react';
import { stagger } from '@/components/AuthShell';
import Chip from '@/components/Chip';
import FormField, { FormAlert, inputClass, textareaClass } from '@/components/FormField';
import { SECTION_LABEL } from '@/components/home/Band';
import {
  BTN_DANGER,
  BTN_DANGER_OUTLINE,
  BTN_OUTLINE,
  BTN_PRIMARY,
  CARD,
  PageHeader,
  PageSkeleton,
  Pill,
  SignInNotice,
} from '@/components/ui';
import { api, ApiError } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { initials } from '@/lib/labels';

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

/** National ID is sensitive: show only the last four digits in the summary. */
function maskNik(nik: string): string {
  return nik.length > 4 ? '•'.repeat(nik.length - 4) + nik.slice(-4) : nik;
}

export default function ProfilePage() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [skillsFailed, setSkillsFailed] = useState(false);
  const [skillIds, setSkillIds] = useState<string[]>([]);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [password, setPassword] = useState('');
  const [deleteError, setDeleteError] = useState('');

  const allowed = !!user && (user.role === 'applicant' || user.role === 'alumni');

  const loadProfile = useCallback(() => {
    setError('');
    api<Profile>('/me/profile')
      .then((p) => {
        setProfile(p);
        setForm(toForm(p));
        if (p.role === 'applicant') setSkillIds(p.skills.map((s) => s.id));
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load the profile.'));
  }, []);

  useEffect(() => {
    if (allowed) loadProfile();
  }, [allowed, loadProfile]);

  const loadSkills = useCallback(() => {
    setSkillsFailed(false);
    api<Skill[]>('/skills')
      .then(setSkills)
      .catch(() => setSkillsFailed(true));
  }, []);

  useEffect(() => {
    if (user?.role === 'applicant') loadSkills();
  }, [user?.role, loadSkills]);

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

  if (loading) return <PageSkeleton />;

  if (!user) {
    return (
      <SignInNotice title="Profile">
        Please{' '}
        <Link className="font-medium text-zinc-900 underline underline-offset-4" href="/login">
          sign in
        </Link>{' '}
        to see your profile.
      </SignInNotice>
    );
  }

  if (!allowed) {
    return <SignInNotice title="Profile">Admin accounts do not have a profile.</SignInNotice>;
  }

  const isApplicant = profile?.role === 'applicant';
  const displayName = form?.full_name.trim() || user.username;
  const chosenSkills = skills.filter((s) => skillIds.includes(s.id));

  return (
    <div className="py-4">
      <PageHeader
        eyebrow="Account"
        title="Your profile"
        subtitle={
          user.role === 'alumni'
            ? 'This is what the admin reviews before approving your alumni account.'
            : 'Vacancy owners see these details when you apply. Keep them current.'
        }
      />

      {!form && !error && <PageSkeleton />}

      {!form && error && (
        <div className="mt-10 flex flex-col items-start gap-3">
          <FormAlert>{error}</FormAlert>
          <button type="button" className={BTN_OUTLINE} onClick={loadProfile}>
            Try again
          </button>
        </div>
      )}

      {form && profile && (
        <div className="mt-10 grid items-start gap-6 lg:grid-cols-[minmax(0,4fr)_minmax(0,8fr)]">
          {/* Summary */}
          <aside className="rise flex flex-col gap-6 lg:sticky lg:top-24" style={stagger(1)}>
            <section className={CARD} aria-label="Account summary">
              <div className="flex items-center gap-4">
                <span
                  aria-hidden
                  className="grid h-16 w-16 shrink-0 place-items-center rounded-full bg-zinc-900 text-lg font-semibold tracking-tight text-zinc-50"
                >
                  {initials(displayName)}
                </span>
                <div className="min-w-0">
                  <p className="truncate text-xl font-semibold tracking-tight text-zinc-900">{displayName}</p>
                  <p className="truncate font-mono text-xs text-zinc-500">@{user.username}</p>
                </div>
              </div>

              <div className="mt-6 flex flex-wrap gap-2">
                <Pill tone="solid">{user.role}</Pill>
                <Pill tone={user.status === 'active' ? 'outline' : 'muted'}>{user.status}</Pill>
              </div>

              <dl className="mt-8 divide-y divide-zinc-200 border-y border-zinc-200 text-sm">
                {profile.role === 'applicant' ? (
                  <>
                    <Row label="Email" value={profile.email} />
                    <Row label="Phone" value={profile.phone} />
                    <Row label="National ID" value={maskNik(profile.nik)} mono />
                    <Row label="Class year" value={String(profile.angkatan)} mono />
                  </>
                ) : (
                  <>
                    <Row label="Company" value={profile.company || 'Not set'} muted={!profile.company} />
                    <Row label="Class year" value={profile.angkatan ? String(profile.angkatan) : 'Not set'} mono muted={!profile.angkatan} />
                  </>
                )}
              </dl>
            </section>

            {profile.role === 'alumni' && <Verification v={profile.verification} />}
          </aside>

          {/* Form */}
          <div className="flex flex-col gap-6">
            <form
              onSubmit={save}
              noValidate
              className={`rise flex flex-col gap-10 ${CARD}`}
              style={stagger(2)}
              aria-label="Edit profile"
            >
              <section className="flex flex-col gap-5">
                <h2 className={SECTION_LABEL}>{isApplicant ? 'Personal details' : 'Alumni details'}</h2>
                <FormField label="Full name" error={fields.full_name}>
                  <input className={inputClass} value={form.full_name} onChange={set('full_name')} autoComplete="name" />
                </FormField>

                {profile.role === 'alumni' && (
                  <FormField label="Company" error={fields.company}>
                    <input className={inputClass} value={form.company} onChange={set('company')} autoComplete="organization" />
                  </FormField>
                )}

                {profile.role === 'applicant' && (
                  <>
                    <div className="grid gap-5 sm:grid-cols-2">
                      <FormField label="Email" error={fields.email}>
                        <input className={inputClass} type="email" value={form.email} onChange={set('email')} autoComplete="email" />
                      </FormField>
                      <FormField label="Phone" error={fields.phone}>
                        <input className={inputClass} value={form.phone} onChange={set('phone')} autoComplete="tel" inputMode="tel" />
                      </FormField>
                    </div>
                    <FormField label="National ID number" error={fields.nik} hint="16 digits.">
                      <input className={inputClass} value={form.nik} onChange={set('nik')} inputMode="numeric" />
                    </FormField>
                    <FormField label="Address" error={fields.address}>
                      <textarea className={textareaClass} rows={3} value={form.address} onChange={set('address')} />
                    </FormField>
                    <FormField label="Birth date" error={fields.birth_date}>
                      <input className={inputClass} type="date" value={form.birth_date} onChange={set('birth_date')} />
                    </FormField>
                  </>
                )}

                <FormField label="Class year (angkatan)" error={fields.angkatan}>
                  <input className={inputClass} inputMode="numeric" value={form.angkatan} onChange={set('angkatan')} />
                </FormField>
              </section>

              {profile.role === 'applicant' && (
                <section className="flex flex-col gap-6">
                  <h2 className={SECTION_LABEL}>Preferences</h2>

                  <fieldset className="flex flex-col gap-2 text-sm" data-invalid={fields.skill_ids ? 'true' : undefined}>
                    <div className="flex items-baseline justify-between">
                      <legend className="font-medium text-zinc-900">Skills</legend>
                      <span className="font-mono text-xs text-zinc-500">{skillIds.length}/30</span>
                    </div>
                    {skills.length === 0 && !skillsFailed && (
                      <div aria-hidden className="flex animate-pulse flex-wrap gap-2">
                        {[84, 64, 96, 72, 88, 60, 76].map((w, i) => (
                          <div key={i} className="h-9 rounded-full bg-zinc-200/70" style={{ width: w }} />
                        ))}
                      </div>
                    )}
                    {skillsFailed && (
                      <p className="flex items-center gap-2 text-zinc-600">
                        The skill list is unavailable right now.
                        <button type="button" onClick={loadSkills} className="font-medium text-zinc-900 underline-offset-4 hover:underline">
                          Try again
                        </button>
                      </p>
                    )}
                    {skills.length > 0 && (
                      <div className="flex flex-wrap gap-2">
                        {skills.map((s) => (
                          <Chip key={s.id} selected={skillIds.includes(s.id)} onClick={() => toggleSkill(s.id)}>
                            {s.name}
                          </Chip>
                        ))}
                      </div>
                    )}
                    {fields.skill_ids ? (
                      <p role="alert" className="text-[13px] text-red-700">
                        {fields.skill_ids}
                      </p>
                    ) : (
                      <p className="text-[13px] text-zinc-500">
                        Used to recommend vacancies.
                        {chosenSkills.length > 0 && ' Selected: ' + chosenSkills.map((s) => s.name).join(', ') + '.'}
                      </p>
                    )}
                  </fieldset>

                  <fieldset className="flex flex-col gap-2 text-sm">
                    <legend className="mb-2 font-medium text-zinc-900">Job type you are looking for</legend>
                    <div role="group" className="flex flex-wrap gap-2">
                      {TYPES.map((t) => (
                        <Chip
                          key={t.value}
                          selected={form.preferred_type === t.value}
                          onClick={() => {
                            setSaved(false);
                            setForm((f) => (f ? { ...f, preferred_type: f.preferred_type === t.value ? '' : t.value } : f));
                          }}
                        >
                          {t.label}
                        </Chip>
                      ))}
                    </div>
                    <p className="text-[13px] text-zinc-500">Optional. Select again to clear.</p>
                  </fieldset>

                  <FormField label="Preferred location" error={fields.preferred_location} hint="Optional.">
                    <input className={inputClass} value={form.preferred_location} onChange={set('preferred_location')} />
                  </FormField>
                </section>
              )}

              {error && <FormAlert>{error}</FormAlert>}

              <div className="flex flex-wrap items-center gap-4">
                <button className={BTN_PRIMARY} type="submit" disabled={busy}>
                  {busy ? 'Saving...' : 'Save changes'}
                </button>
                <p role="status" aria-live="polite" className="min-h-5 text-sm text-zinc-600">
                  {saved && (
                    <span className="inline-flex items-center gap-2">
                      <CheckCircle size={18} weight="fill" className="text-zinc-900" />
                      Profile saved.
                    </span>
                  )}
                </p>
              </div>
            </form>

            {/* Danger zone */}
            <section
              className="rise rounded-[2.5rem] border border-red-200/70 bg-red-50/40 p-8 md:p-10"
              style={stagger(3)}
              aria-label="Delete account"
            >
              <h2 className="text-xs font-semibold uppercase tracking-[0.14em] text-red-800">Delete account</h2>
              <p className="mt-3 max-w-[52ch] text-sm leading-relaxed text-zinc-600">
                This removes your account, profile, applications, testimonials and uploaded files. It cannot be undone.
              </p>
              {!deleting ? (
                <button className={`${BTN_DANGER_OUTLINE} mt-6`} type="button" onClick={() => setDeleting(true)}>
                  Delete my account
                </button>
              ) : (
                <form onSubmit={deleteAccount} noValidate className="mt-6 flex max-w-sm flex-col gap-4">
                  <FormField label="Confirm with your password" error={deleteError}>
                    <input
                      className={inputClass}
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      autoComplete="current-password"
                    />
                  </FormField>
                  <div className="flex flex-wrap gap-3">
                    <button className={BTN_DANGER} type="submit" disabled={busy}>
                      {busy ? 'Deleting...' : 'Delete permanently'}
                    </button>
                    <button
                      className={BTN_OUTLINE}
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
        </div>
      )}
    </div>
  );
}

function Row({ label, value, mono, muted }: { label: string; value: string; mono?: boolean; muted?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4 py-3">
      <dt className="text-zinc-500">{label}</dt>
      <dd className={`min-w-0 truncate text-right ${mono ? 'font-mono text-xs' : ''} ${muted ? 'text-zinc-400' : 'font-medium text-zinc-900'}`}>
        {value}
      </dd>
    </div>
  );
}

function Verification({ v }: { v: { state: string; reason: string | null } }) {
  const approved = v.state === 'approved';
  const rejected = v.state === 'rejected';
  return (
    <section
      className={`rounded-[2.5rem] p-8 ${approved ? 'bg-zinc-950 text-zinc-50' : 'border border-zinc-200 bg-white text-zinc-900'
        }`}
      aria-label="Verification"
    >
      <div className="flex items-center gap-3">
        <span
          aria-hidden
          className={`grid h-10 w-10 place-items-center rounded-full ${approved ? 'bg-white/10' : 'bg-zinc-100 text-zinc-700'}`}
        >
          {rejected ? <Warning size={20} /> : <ShieldCheck size={20} />}
        </span>
        <div>
          <p className={`text-xs font-semibold uppercase tracking-[0.14em] ${approved ? 'text-zinc-400' : 'text-zinc-500'}`}>
            Verification
          </p>
          <p className="text-lg font-semibold capitalize tracking-tight">{v.state}</p>
        </div>
      </div>
      {v.reason && (
        <p className={`mt-5 text-sm leading-relaxed ${approved ? 'text-zinc-300' : 'text-zinc-600'}`}>
          <span className="font-medium">Reason:</span> {v.reason}
        </p>
      )}
      {!approved && (
        <p className="mt-4 text-sm leading-relaxed text-zinc-500">
          Full name, company and class year are required before approval.
        </p>
      )}
    </section>
  );
}