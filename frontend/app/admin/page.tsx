'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/lib/auth';
import { api, ApiError } from '@/lib/api';

type Tab = 'overview' | 'alumni' | 'users' | 'testimonials';
const TABS: { key: Tab; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'alumni', label: 'Alumni verification' },
  { key: 'users', label: 'Users' },
  { key: 'testimonials', label: 'Testimonials' },
];

type Page<T> = { items: T[]; next_cursor: string | null };

function errText(e: unknown, fallback: string): string {
  return e instanceof ApiError ? e.message : fallback;
}

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleString() : '-';
}

function useList<T>(path: string, query: Record<string, string>, enabled: boolean) {
  const [items, setItems] = useState<T[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState('');
  const queryKey = JSON.stringify(query);

  const load = useCallback(
    async (after: string | null) => {
      setError('');
      try {
        const res = await api<Page<T>>(path, {
          query: { ...(JSON.parse(queryKey) as Record<string, string>), limit: 20, cursor: after },
        });
        setItems((old) => (after && old ? [...old, ...res.items] : res.items));
        setCursor(res.next_cursor);
      } catch (e) {
        setError(errText(e, 'Could not load the list.'));
      }
    },
    [path, queryKey],
  );

  useEffect(() => {
    if (!enabled) return;
    setItems(null);
    load(null);
  }, [enabled, load]);

  return { items, setItems, cursor, error, setError, more: () => load(cursor), reload: () => load(null) };
}

function MoreButton({ cursor, onClick }: { cursor: string | null; onClick: () => void }) {
  if (!cursor) return null;
  return (
    <button onClick={onClick} className="mt-3 rounded border px-3 py-1 text-sm">
      Show more
    </button>
  );
}

type Overview = {
  users_by_role: Record<string, number>;
  users_by_status: Record<string, number>;
  jobs_by_status: Record<string, number>;
  applications_by_status: Record<string, number>;
  documents_by_type: Record<string, number>;
  alumni_awaiting_decision: number;
};

function OverviewTab() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api<Overview>('/admin/overview')
      .then(setData)
      .catch((e) => setError(errText(e, 'Could not load the overview.')));
  }, []);

  if (error) return <p className="text-sm text-red-700">{error}</p>;
  if (!data) return <p className="text-sm text-gray-600">Loading...</p>;

  const groups: [string, Record<string, number>][] = [
    ['Users by role', data.users_by_role],
    ['Users by status', data.users_by_status],
    ['Vacancies by status', data.jobs_by_status],
    ['Applications by status', data.applications_by_status],
    ['Documents by type', data.documents_by_type],
  ];

  return (
    <div className="space-y-4">
      <p className="text-sm">
        Alumni awaiting a decision: <strong>{data.alumni_awaiting_decision}</strong>
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        {groups.map(([title, counts]) => (
          <div key={title} className="rounded border p-3">
            <h3 className="font-medium">{title}</h3>
            {Object.keys(counts).length === 0 ? (
              <p className="text-sm text-gray-600">No data.</p>
            ) : (
              <ul className="mt-1 text-sm">
                {Object.entries(counts).map(([k, v]) => (
                  <li key={k}>
                    {k}: {v}
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

type AlumniItem = {
  id: string;
  username: string;
  account_status: string;
  verification: { state: string; reason: string | null };
  full_name: string | null;
  company: string | null;
  angkatan: number | null;
  profile_complete: boolean;
  created_at: string;
};

function AlumniTab() {
  const [state, setState] = useState('pending');
  const list = useList<AlumniItem>('/admin/alumni', { state }, true);
  const [busyId, setBusyId] = useState('');
  const [rejectId, setRejectId] = useState('');
  const [reason, setReason] = useState('');

  async function act(id: string, action: 'approve' | 'reject') {
    setBusyId(id);
    list.setError('');
    try {
      await api(`/admin/alumni/${id}/${action}`, {
        method: 'POST',
        body: action === 'reject' ? { reason: reason.trim() } : undefined,
      });
      setRejectId('');
      setReason('');
      list.setItems((old) => (old ?? []).filter((a) => a.id !== id));
    } catch (e) {
      list.setError(errText(e, 'The action failed.'));
    } finally {
      setBusyId('');
    }
  }

  return (
    <div>
      <label className="text-sm">
        State{' '}
        <select value={state} onChange={(e) => setState(e.target.value)} className="rounded border p-1">
          <option value="pending">Pending</option>
          <option value="rejected">Rejected</option>
          <option value="approved">Approved</option>
        </select>
      </label>
      {list.error && <p className="mt-3 text-sm text-red-700">{list.error}</p>}
      {!list.items && !list.error && <p className="mt-3 text-sm text-gray-600">Loading...</p>}
      {list.items && list.items.length === 0 && <p className="mt-3 text-sm">No alumni in this state.</p>}
      {list.items && list.items.length > 0 && (
        <ul className="mt-3 divide-y rounded border">
          {list.items.map((a) => (
            <li key={a.id} className="p-3 text-sm">
              <p className="font-medium">
                {a.full_name || '(no name)'} <span className="text-xs text-gray-500">@{a.username}</span>
              </p>
              <p className="text-gray-700">
                {a.company || '(no company)'} · class of {a.angkatan ?? '-'} · account {a.account_status} ·
                profile {a.profile_complete ? 'complete' : 'incomplete'}
              </p>
              <p className="text-xs text-gray-500">Registered {formatDate(a.created_at)}</p>
              {a.verification.reason && (
                <p className="text-xs text-gray-700">Rejection reason: {a.verification.reason}</p>
              )}
              {state === 'pending' && (
                <div className="mt-2">
                  <div className="flex gap-2">
                    <button
                      disabled={busyId === a.id}
                      onClick={() => act(a.id, 'approve')}
                      className="rounded border px-3 py-1 disabled:opacity-50"
                    >
                      Approve
                    </button>
                    <button
                      disabled={busyId === a.id}
                      onClick={() => {
                        setRejectId(rejectId === a.id ? '' : a.id);
                        setReason('');
                      }}
                      className="rounded border px-3 py-1 disabled:opacity-50"
                    >
                      Reject
                    </button>
                  </div>
                  {rejectId === a.id && (
                    <div className="mt-2">
                      <textarea
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                        maxLength={500}
                        rows={2}
                        placeholder="Reason (up to 500 characters)"
                        className="w-full rounded border p-2"
                      />
                      <button
                        disabled={busyId === a.id || !reason.trim()}
                        onClick={() => act(a.id, 'reject')}
                        className="mt-1 rounded border px-3 py-1 disabled:opacity-50"
                      >
                        Confirm rejection
                      </button>
                    </div>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      <MoreButton cursor={list.cursor} onClick={list.more} />
    </div>
  );
}

type UserItem = {
  id: string;
  username: string;
  role: string;
  status: string;
  created_at: string;
  last_login_at: string | null;
};

function UsersTab() {
  const [role, setRole] = useState('');
  const [status, setStatus] = useState('');
  const [qInput, setQInput] = useState('');
  const [q, setQ] = useState('');
  const query: Record<string, string> = {};
  if (role) query.role = role;
  if (status) query.status = status;
  if (q) query.q = q;
  const list = useList<UserItem>('/admin/users', query, true);
  const [busyId, setBusyId] = useState('');

  async function setUserStatus(user: UserItem, next: 'active' | 'suspended') {
    if (next === 'suspended' && !window.confirm(`Suspend ${user.username}?`)) return;
    setBusyId(user.id);
    list.setError('');
    try {
      await api(`/admin/users/${user.id}/status`, { method: 'PATCH', body: { status: next } });
      list.setItems((old) => (old ?? []).map((u) => (u.id === user.id ? { ...u, status: next } : u)));
    } catch (e) {
      list.setError(errText(e, 'Could not change the status.'));
    } finally {
      setBusyId('');
    }
  }

  return (
    <div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setQ(qInput.trim());
        }}
        className="flex flex-wrap items-end gap-2 text-sm"
      >
        <label>
          Search
          <input
            value={qInput}
            onChange={(e) => setQInput(e.target.value)}
            maxLength={64}
            className="ml-1 rounded border p-1"
          />
        </label>
        <label>
          Role{' '}
          <select value={role} onChange={(e) => setRole(e.target.value)} className="rounded border p-1">
            <option value="">All</option>
            <option value="applicant">Applicant</option>
            <option value="alumni">Alumni</option>
            <option value="admin">Admin</option>
          </select>
        </label>
        <label>
          Status{' '}
          <select value={status} onChange={(e) => setStatus(e.target.value)} className="rounded border p-1">
            <option value="">All</option>
            <option value="active">Active</option>
            <option value="pending">Pending</option>
            <option value="suspended">Suspended</option>
          </select>
        </label>
        <button type="submit" className="rounded border px-3 py-1">
          Search
        </button>
      </form>
      {list.error && <p className="mt-3 text-sm text-red-700">{list.error}</p>}
      {!list.items && !list.error && <p className="mt-3 text-sm text-gray-600">Loading...</p>}
      {list.items && list.items.length === 0 && <p className="mt-3 text-sm">No users found.</p>}
      {list.items && list.items.length > 0 && (
        <ul className="mt-3 divide-y rounded border">
          {list.items.map((u) => (
            <li key={u.id} className="flex flex-wrap items-center justify-between gap-2 p-3 text-sm">
              <div>
                <p className="font-medium">{u.username}</p>
                <p className="text-gray-700">
                  {u.role} · {u.status}
                </p>
                <p className="text-xs text-gray-500">
                  Created {formatDate(u.created_at)} · last login {formatDate(u.last_login_at)}
                </p>
              </div>
              {u.role !== 'admin' && (
                <button
                  disabled={busyId === u.id}
                  onClick={() => setUserStatus(u, u.status === 'suspended' ? 'active' : 'suspended')}
                  className="rounded border px-3 py-1 disabled:opacity-50"
                >
                  {u.status === 'suspended' ? 'Reactivate' : 'Suspend'}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      <MoreButton cursor={list.cursor} onClick={list.more} />
    </div>
  );
}

type TestimonialItem = {
  id: string;
  content: string;
  show_name: boolean;
  status: string;
  created_at: string;
  display_first_name: string | null;
  display_company: string | null;
};

function TestimonialsTab() {
  const [status, setStatus] = useState('pending');
  const list = useList<TestimonialItem>('/admin/testimonials', { status }, true);
  const [busyId, setBusyId] = useState('');

  async function moderate(id: string, next: 'approved' | 'hidden') {
    setBusyId(id);
    list.setError('');
    try {
      await api(`/admin/testimonials/${id}`, { method: 'PATCH', body: { status: next } });
      list.setItems((old) => (old ?? []).filter((t) => t.id !== id));
    } catch (e) {
      list.setError(errText(e, 'Could not update the testimonial.'));
    } finally {
      setBusyId('');
    }
  }

  return (
    <div>
      <label className="text-sm">
        Status{' '}
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="rounded border p-1">
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="hidden">Hidden</option>
        </select>
      </label>
      {list.error && <p className="mt-3 text-sm text-red-700">{list.error}</p>}
      {!list.items && !list.error && <p className="mt-3 text-sm text-gray-600">Loading...</p>}
      {list.items && list.items.length === 0 && <p className="mt-3 text-sm">No testimonials with this status.</p>}
      {list.items && list.items.length > 0 && (
        <ul className="mt-3 divide-y rounded border">
          {list.items.map((t) => (
            <li key={t.id} className="p-3 text-sm">
              <p className="whitespace-pre-wrap">{t.content}</p>
              <p className="mt-1 text-xs text-gray-500">
                {t.display_first_name || 'Anonymous'}
                {t.display_company ? `, ${t.display_company}` : ''} · {t.show_name ? 'name shown' : 'name hidden'} ·{' '}
                {formatDate(t.created_at)}
              </p>
              <div className="mt-2 flex gap-2">
                {status !== 'approved' && (
                  <button
                    disabled={busyId === t.id}
                    onClick={() => moderate(t.id, 'approved')}
                    className="rounded border px-3 py-1 disabled:opacity-50"
                  >
                    Approve
                  </button>
                )}
                {status !== 'hidden' && (
                  <button
                    disabled={busyId === t.id}
                    onClick={() => moderate(t.id, 'hidden')}
                    className="rounded border px-3 py-1 disabled:opacity-50"
                  >
                    Hide
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      <MoreButton cursor={list.cursor} onClick={list.more} />
    </div>
  );
}

export default function AdminPage() {
  const { user, loading } = useAuth();
  const [tab, setTab] = useState<Tab>('overview');

  if (loading) return <p className="text-sm text-gray-600">Loading...</p>;
  if (!user || user.role !== 'admin' || user.status !== 'active') {
    return (
      <p className="text-sm">
        Only administrators can open this page.{' '}
        {!user && (
          <Link href="/login" className="underline">
            Sign in
          </Link>
        )}
      </p>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold">Admin</h1>
      <div className="mt-3 flex flex-wrap gap-2 border-b pb-2 text-sm">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`rounded border px-3 py-1 ${tab === t.key ? 'bg-gray-200 font-medium' : ''}`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="mt-4">
        {tab === 'overview' && <OverviewTab />}
        {tab === 'alumni' && <AlumniTab />}
        {tab === 'users' && <UsersTab />}
        {tab === 'testimonials' && <TestimonialsTab />}
      </div>
    </div>
  );
}
