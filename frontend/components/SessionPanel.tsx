'use client';

import { useState } from 'react';
import { ApiError } from '@/lib/api';
import { useAuth } from '@/lib/auth';

export default function SessionPanel() {
  const { user, loading, login, logout } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  if (loading) return <p className="text-sm text-gray-600">Checking session...</p>;

  if (user) {
    return (
      <div className="text-sm">
        <p>
          Signed in as <strong>{user.username}</strong> ({user.role}, {user.status})
        </p>
        <button className="mt-2 rounded border px-3 py-1" onClick={() => logout()}>
          Sign out
        </button>
      </div>
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    try {
      await login(username, password);
      setPassword('');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong.');
    }
  }

  return (
    <form onSubmit={submit} className="flex max-w-xs flex-col gap-2 text-sm">
      <input className="rounded border px-2 py-1" placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} />
      <input className="rounded border px-2 py-1" type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />
      {error && <p className="text-red-700">{error}</p>}
      <button className="rounded border px-3 py-1" type="submit">
        Sign in
      </button>
    </form>
  );
}
