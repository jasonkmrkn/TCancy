'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import FormField, { inputClass } from '@/components/FormField';
import { ApiError } from '@/lib/api';
import { useAuth } from '@/lib/auth';

export default function LoginPage() {
  const { user, loading, login, logout } = useAuth();
  const router = useRouter();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [fields, setFields] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  if (loading) return <p className="text-sm text-gray-600">Checking session...</p>;

  if (user) {
    return (
      <div className="max-w-sm text-sm">
        <h1 className="text-2xl font-bold">Sign in</h1>
        <p className="mt-4">
          You are signed in as <strong>{user.username}</strong>.
        </p>
        <div className="mt-3 flex gap-2">
          <Link className="rounded border px-3 py-1" href="/">
            Go to home
          </Link>
          <button className="rounded border px-3 py-1" onClick={() => logout()}>
            Sign out
          </button>
        </div>
      </div>
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
    <div className="max-w-sm">
      <h1 className="text-2xl font-bold">Sign in</h1>
      <form onSubmit={submit} className="mt-4 flex flex-col gap-3">
        <FormField label="Username" error={fields.username}>
          <input className={inputClass} value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
        </FormField>
        <FormField label="Password" error={fields.password}>
          <input className={inputClass} type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
        </FormField>
        {error && <p className="text-sm text-red-700">{error}</p>}
        <button className="rounded border px-3 py-1 text-sm" type="submit" disabled={busy}>
          {busy ? 'Signing in...' : 'Sign in'}
        </button>
      </form>
      <p className="mt-4 text-sm text-gray-600">
        No account yet?{' '}
        <Link className="underline" href="/register">
          Register
        </Link>
      </p>
    </div>
  );
}
