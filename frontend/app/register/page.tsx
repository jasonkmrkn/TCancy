'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import { Info } from '@phosphor-icons/react';
import AuthShell, { stagger } from '@/components/AuthShell';
import FormField, { FormAlert, inputClass, primaryButtonClass, textareaClass } from '@/components/FormField';
import PasswordInput from '@/components/PasswordInput';
import { ApiError } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { auth as authApi, skills as skillsApi, type JobType, type Skill } from '@/lib/endpoints';

type Kind = 'applicant' | 'alumni';
type SkillsState = 'loading' | 'ready' | 'error';

const TYPES = [
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

const THIS_YEAR = new Date().getFullYear();

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

const SECTION = 'text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500';
const CHIP =
  'rounded-full border px-4 py-2 text-sm transition duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] active:translate-y-[1px] active:scale-[0.98] ' +
  'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900';

function Chip({ selected, onClick, children }: { selected: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onClick}
      className={`${CHIP} ${selected
        ? 'border-zinc-900 bg-zinc-900 text-zinc-50'
        : 'border-zinc-200 bg-white text-zinc-700 hover:border-zinc-400'
        }`}
    >
      {children}
    </button>
  );
}

function FormSkeleton() {
  return (
    <div aria-hidden className="flex animate-pulse flex-col gap-5">
      <div className="h-9 w-56 rounded-full bg-zinc-200/70" />
      <div className="h-5 w-96 max-w-full rounded-full bg-zinc-200/70" />
      <div className="mt-6 h-14 rounded-full bg-zinc-200/70" />
      <div className="h-12 rounded-full bg-zinc-200/70" />
      <div className="grid gap-5 sm:grid-cols-2">
        <div className="h-12 rounded-full bg-zinc-200/70" />
        <div className="h-12 rounded-full bg-zinc-200/70" />
      </div>
      <div className="h-12 rounded-full bg-zinc-200/70" />
    </div>
  );
}

export default function RegisterPage() {
  const { user, loading, login } = useAuth();
  const router = useRouter();
  const [kind, setKind] = useState<Kind>('applicant');
  const [form, setForm] = useState(EMPTY);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [skillsState, setSkillsState] = useState<SkillsState>('loading');
  const [skillIds, setSkillIds] = useState<string[]>([]);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const loadSkills = useCallback(() => {
    setSkillsState('loading');
    skillsApi
      .list()
      .then((list) => {
        setSkills(list);
        setSkillsState('ready');
      })
      .catch(() => setSkillsState('error'));
  }, []);

  useEffect(() => {
    loadSkills();
  }, [loadSkills]);

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
      if (!form.full_name.trim()) out.full_name = 'Full name is required.';
      else if (form.full_name.trim().length > 200) out.full_name = 'Full name must be at most 200 characters.';
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email) || form.email.length > 254) out.email = 'Enter a valid email address.';
      if (!/^\+?\d{8,15}$/.test(form.phone)) out.phone = 'Phone must be 8-15 digits, optionally starting with +.';
      if (!/^\d{16}$/.test(form.nik)) out.nik = 'National ID number must be exactly 16 digits.';
      if (!form.address.trim()) out.address = 'Address is required.';
      else if (form.address.trim().length > 500) out.address = 'Address must be at most 500 characters.';
      if (!form.birth_date) out.birth_date = 'Birth date is required.';
      const year = Number(form.angkatan);
      if (!Number.isInteger(year) || year < 1990 || year > THIS_YEAR) {
        out.angkatan = 'Class year must be between 1990 and ' + THIS_YEAR + '.';
      }
      if (skillIds.length < 1 || skillIds.length > 30) out.skill_ids = 'Pick 1 to 30 skills.';
      if (form.preferred_location.length > 100) out.preferred_location = 'Preferred location must be at most 100 characters.';
    }
    return out;
  }

  function focusFirstInvalid() {
    requestAnimationFrame(() => {
      document.querySelector<HTMLElement>('[data-invalid="true"] :is(input, textarea, button)')?.focus();
    });
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    const problems = validate();
    setFields(problems);
    if (Object.keys(problems).length > 0) {
      focusFirstInvalid();
      return;
    }
    setBusy(true);
    const username = form.username.trim().toLowerCase();
    try {
      if (kind === 'alumni') {
        await authApi.registerAlumni({ username, password: form.password });
      } else {
        await authApi.register({
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
            preferred_type: (form.preferred_type || null) as JobType | null,
            preferred_location: form.preferred_location.trim() || null,
          },
        });
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        setFields(mapFields(err));
        focusFirstInvalid();
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

  if (loading) {
    return (
      <AuthShell>
        <FormSkeleton />
      </AuthShell>
    );
  }

  if (user) {
    return (
      <AuthShell>
        <h1 className="text-3xl font-semibold tracking-tight text-zinc-900">Create account</h1>
        <p className="mt-2 text-zinc-500">
          You are already signed in as <span className="font-medium text-zinc-900">{user.username}</span>. Sign out first to create
          another account.
        </p>
      </AuthShell>
    );
  }

  return (
    <AuthShell>
      <header className="rise" style={stagger(0)}>
        <h1 className="text-3xl font-semibold tracking-tight text-zinc-900">Create account</h1>
        <p className="mt-2 text-zinc-500">Register as an applicant to apply, or as an alumnus to post vacancies.</p>
      </header>

      {/* Applicant / Alumni segmented control */}
      <div
        role="radiogroup"
        aria-label="Account type"
        className="rise relative mt-8 grid grid-cols-2 rounded-full bg-zinc-100 p-1"
        style={stagger(1)}
      >
        <span
          aria-hidden
          className={`absolute inset-y-1 left-1 w-[calc(50%-0.25rem)] rounded-full bg-white shadow-[0_2px_8px_-2px_rgba(24,24,27,0.12)] transition-transform duration-500 ease-[cubic-bezier(0.16,1,0.3,1)] ${kind === 'alumni' ? 'translate-x-full' : ''
            }`}
        />
        {(['applicant', 'alumni'] as Kind[]).map((k) => (
          <button
            key={k}
            type="button"
            role="radio"
            aria-checked={kind === k}
            onClick={() => {
              setKind(k);
              setFields({});
              setError('');
            }}
            className={`relative min-h-12 rounded-full text-sm font-medium transition-colors duration-300 ${kind === k ? 'text-zinc-900' : 'text-zinc-500 hover:text-zinc-700'
              }`}
          >
            {k === 'applicant' ? 'Applicant' : 'Alumni'}
          </button>
        ))}
      </div>

      {kind === 'alumni' && (
        <div className="mt-4 flex items-start gap-3 rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-600">
          <Info size={18} weight="regular" className="mt-0.5 shrink-0 text-zinc-500" />
          <p>Alumni accounts stay pending until an admin approves them. After signing in, complete your profile.</p>
        </div>
      )}

      <form onSubmit={submit} className="mt-10 flex flex-col gap-10" noValidate aria-busy={busy}>
        <section className="rise flex flex-col gap-5" style={stagger(2)}>
          <h2 className={SECTION}>Account</h2>
          <FormField label="Username" error={fields.username} hint="3 to 64 characters. Lowercase only.">
            <input
              className={inputClass}
              value={form.username}
              onChange={set('username')}
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
            />
          </FormField>
          <div className="grid items-start gap-5 sm:grid-cols-2">
            <FormField label="Password" error={fields.password} hint="At least 8 characters.">
              <PasswordInput value={form.password} onChange={set('password')} autoComplete="new-password" />
            </FormField>
            <FormField label="Confirm password" error={fields.confirm}>
              <PasswordInput value={form.confirm} onChange={set('confirm')} autoComplete="new-password" />
            </FormField>
          </div>
        </section>

        {kind === 'applicant' && (
          <section className="rise flex flex-col gap-5" style={stagger(3)}>
            <h2 className={SECTION}>Personal details</h2>
            <FormField label="Full name" error={fields.full_name}>
              <input className={inputClass} value={form.full_name} onChange={set('full_name')} autoComplete="name" />
            </FormField>
            <div className="grid items-start gap-5 sm:grid-cols-2">
              <FormField label="Email" error={fields.email}>
                <input className={inputClass} type="email" value={form.email} onChange={set('email')} autoComplete="email" />
              </FormField>
              <FormField label="Phone number" error={fields.phone} hint="Digits only, optionally starting with +.">
                <input
                  className={inputClass}
                  type="tel"
                  value={form.phone}
                  onChange={set('phone')}
                  placeholder="081234567890"
                  autoComplete="tel"
                />
              </FormField>
            </div>
            <div className="grid items-start gap-5 sm:grid-cols-2">
              <FormField label="NIK" error={fields.nik} hint="16 digits. Shown only to owners of vacancies you apply to.">
                <input className={inputClass} value={form.nik} onChange={set('nik')} inputMode="numeric" maxLength={16} />
              </FormField>
              <FormField label="Date of birth" error={fields.birth_date}>
                <input className={inputClass} type="date" value={form.birth_date} onChange={set('birth_date')} />
              </FormField>
            </div>
            <FormField label="Address" error={fields.address}>
              <textarea className={textareaClass} rows={3} value={form.address} onChange={set('address')} autoComplete="street-address" />
            </FormField>
            <div className="grid items-start gap-5 sm:grid-cols-2">
              <FormField label="Class year" error={fields.angkatan} hint={`Year of entry, between 1990 and ${THIS_YEAR}.`}>
                <input className={inputClass} inputMode="numeric" maxLength={4} value={form.angkatan} onChange={set('angkatan')} />
              </FormField>
              <FormField label="Preferred location" error={fields.preferred_location} hint="Optional.">
                <input className={inputClass} value={form.preferred_location} onChange={set('preferred_location')} />
              </FormField>
            </div>
          </section>
        )}

        {kind === 'applicant' && (
          <section className="rise flex flex-col gap-5" style={stagger(4)}>
            <h2 className={SECTION}>Preferences</h2>

            <fieldset className="flex flex-col gap-2 text-sm" data-invalid={fields.skill_ids ? 'true' : undefined}>
              <div className="flex items-baseline justify-between">
                <legend className="font-medium text-zinc-900">Skills</legend>
                <span className="font-mono text-xs text-zinc-500">{skillIds.length}/30</span>
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
                  <button
                    type="button"
                    onClick={loadSkills}
                    className="font-medium text-zinc-900 underline-offset-4 hover:underline"
                  >
                    Try again
                  </button>
                </p>
              )}
              {skillsState === 'ready' && skills.length === 0 && (
                <p className="text-zinc-600">No skills have been added yet. Ask an admin to add some, then reload this page.</p>
              )}
              {skillsState === 'ready' && skills.length > 0 && (
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
                <p className="text-[13px] text-zinc-500">Choose at least one, at most 30.</p>
              )}
            </fieldset>

            <fieldset className="flex flex-col gap-2 text-sm">
              <legend className="mb-2 font-medium text-zinc-900">Job type you are looking for</legend>
              <div role="group" className="flex flex-wrap gap-2">
                {TYPES.map((t) => (
                  <Chip
                    key={t.value}
                    selected={form.preferred_type === t.value}
                    onClick={() => setForm((f) => ({ ...f, preferred_type: f.preferred_type === t.value ? '' : t.value }))}
                  >
                    {t.label}
                  </Chip>
                ))}
              </div>
              <p className="text-[13px] text-zinc-500">Optional. Select again to clear.</p>
            </fieldset>
          </section>
        )}

        {error && <FormAlert>{error}</FormAlert>}

        <div className="rise -mt-4" style={stagger(5)}>
          <button className={primaryButtonClass} type="submit" disabled={busy}>
            {busy ? 'Creating account...' : 'Create account'}
          </button>
          <p className="mt-6 text-sm text-zinc-500">
            Already have an account?{' '}
            <Link className="font-medium text-zinc-900 underline-offset-4 hover:underline" href="/login">
              Sign in
            </Link>
          </p>
        </div>
      </form>
    </AuthShell>
  );
}