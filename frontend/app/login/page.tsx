'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import AuthShell, { stagger } from '@/components/AuthShell';
import FormField, { FormAlert, inputClass, primaryButtonClass } from '@/components/FormField';
import PasswordInput from '@/components/PasswordInput';
import { ApiError } from '@/lib/api';
import { useAuth } from '@/lib/auth';

function FormSkeleton() {
  return (
    <div aria-hidden className="flex animate-pulse flex-col gap-5">
      <div className="h-9 w-40 rounded-full bg-zinc-200/70" />
      <div className="h-5 w-72 rounded-full bg-zinc-200/70" />
      <div className="mt-8 h-12 rounded-full bg-zinc-200/70" />
      <div className="h-12 rounded-full bg-zinc-200/70" />
      <div className="h-12 rounded-full bg-zinc-300/70" />
    </div>
  );
}

export default function LoginPage() {
  const { user, loading, login, logout } = useAuth();
  const router = useRouter();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [fields, setFields] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

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
        <h1 className="text-3xl font-semibold tracking-tight text-zinc-900">Sign in</h1>
        <p className="mt-2 text-zinc-500">
          You are signed in as <span className="font-medium text-zinc-900">{user.username}</span>.
        </p>
        <div className="mt-8 grid grid-cols-2 gap-3">
          <Link
            href="/"
            className="flex min-h-12 items-center justify-center rounded-full bg-zinc-900 px-6 text-sm font-medium text-zinc-50 transition duration-300 hover:bg-zinc-800 active:translate-y-[1px] active:scale-[0.98]"
          >
            Go to home
          </Link>
          <button
            onClick={() => logout()}
            className="min-h-12 rounded-full border border-zinc-200 bg-white px-6 text-sm font-medium text-zinc-900 transition duration-300 hover:border-zinc-300 active:translate-y-[1px] active:scale-[0.98]"
          >
            Sign out
          </button>
        </div>
      </AuthShell>
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setFields({});
    if (!username.trim() || !password) {
      setFields({
        ...(username.trim() ? {} : { username: 'Username is required.' }),
        ...(password ? {} : { password: 'Password is required.' }),
      });
      return;
    }
    setBusy(true);
    try {
      await login(username.trim().toLowerCase(), password);
      router.push('/');
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        setFields(err.fields);
      } else {
        setError('Something went wrong.');
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell>
      <header className="rise" style={stagger(0)}>
        <h1 className="text-3xl font-semibold tracking-tight text-zinc-900">Sign in</h1>
        <p className="mt-2 text-zinc-500">Continue to your profile and applications.</p>
      </header>

      <form onSubmit={submit} className="mt-10 flex flex-col gap-5" noValidate aria-busy={busy}>
        <div className="rise" style={stagger(1)}>
          <FormField label="Username" error={fields.username}>
            <input
              className={inputClass}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
            />
          </FormField>
        </div>
        <div className="rise" style={stagger(2)}>
          <FormField label="Password" error={fields.password}>
            <PasswordInput value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
          </FormField>
        </div>
        {error && <FormAlert>{error}</FormAlert>}
        <div className="rise mt-1" style={stagger(3)}>
          <button className={primaryButtonClass} type="submit" disabled={busy}>
            {busy ? 'Signing in...' : 'Sign in'}
          </button>
        </div>
      </form>

      <p className="rise mt-8 text-sm text-zinc-500" style={stagger(4)}>
        No account yet?{' '}
        <Link className="font-medium text-zinc-900 underline-offset-4 hover:underline" href="/register">
          Register
        </Link>
      </p>
    </AuthShell>
  );
}