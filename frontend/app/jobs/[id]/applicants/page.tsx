'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import { NotAllowed, useIsOwnerRole } from '@/components/OwnerGate';
import { api, ApiError, buildUrl } from '@/lib/api';

type Doc = { id: string; ext: string; size: number; created_at: string } | null;
type Applicant = {
  full_name: string;
  email: string;
  angkatan: number;
  skills: { id: string; name: string }[];
  phone: string;
} | null;
type Item = {
  id: string;
  status: string;
  created_at: string;
  applicant: Applicant;
  documents: { cv: Doc; video: Doc };
};
type Page = { items: Item[]; next_cursor: string | null };
type Detail = Item & {
  cover_note: string | null;
  history: { from_status: string | null; to_status: string; note: string | null; created_at: string }[];
};
type Identity = { nik: string; address: string; birth_date: string; ktp_available: boolean };

const NEXT: Record<string, string[]> = {
  submitted: ['shortlisted', 'accepted', 'rejected'],
  shortlisted: ['accepted', 'rejected'],
  accepted: ['shortlisted', 'rejected'],
};

function ApplicantPanel({ item, onChanged }: { item: Item; onChanged: (status: string) => void }) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setDetail(await api<Detail>(`/applications/${item.id}`));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load the application.');
    }
  }, [item.id]);

  useEffect(() => {
    load();
  }, [load]);

  async function showIdentity() {
    setError('');
    try {
      setIdentity(await api<Identity>(`/applications/${item.id}/identity`));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load the identity data.');
    }
  }

  async function changeStatus(status: string) {
    if (note.length > 500) {
      setError('The note can have at most 500 characters.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await api(`/applications/${item.id}/status`, {
        method: 'PATCH',
        body: { status, note: note.trim() || null },
      });
      setNote('');
      onChanged(status);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not change the status.');
    } finally {
      setBusy(false);
    }
  }

  const current = detail?.status ?? item.status;
  const options = NEXT[current] ?? [];

  return (
    <div className="mt-2 space-y-3 rounded border bg-gray-50 p-3">
      {error && <p className="text-red-700">{error}</p>}
      {!detail && !error && <p className="text-gray-600">Loading...</p>}
      {detail && (
        <>
          <p>
            <span className="font-medium">Cover note:</span>{' '}
            {detail.cover_note ? <span className="whitespace-pre-wrap">{detail.cover_note}</span> : 'None'}
          </p>
          <p className="flex flex-wrap gap-3">
            {item.documents.cv ? (
              <a className="underline" href={buildUrl(`/applications/${item.id}/cv`)}>
                Download CV
              </a>
            ) : (
              <span className="text-gray-500">No CV</span>
            )}
            {item.documents.video ? (
              <a className="underline" href={buildUrl(`/applications/${item.id}/video`)}>
                Download intro video
              </a>
            ) : (
              <span className="text-gray-500">No intro video</span>
            )}
            <a className="underline" href={buildUrl(`/applications/${item.id}/identity/ktp`)}>
              Download ID card
            </a>
          </p>
          <div>
            {!identity && (
              <button className="underline" onClick={showIdentity}>
                Show identity data
              </button>
            )}
            {identity && (
              <ul>
                <li>National ID number: {identity.nik}</li>
                <li>Address: {identity.address}</li>
                <li>Birth date: {identity.birth_date}</li>
                <li>ID card uploaded: {identity.ktp_available ? 'yes' : 'no'}</li>
              </ul>
            )}
          </div>
          <div>
            <p className="font-medium">History</p>
            <ul className="list-disc pl-5">
              {detail.history.map((h, i) => (
                <li key={i}>
                  {h.from_status ?? 'start'} → {h.to_status} on {h.created_at.slice(0, 10)}
                  {h.note ? `: ${h.note}` : ''}
                </li>
              ))}
            </ul>
          </div>
          {options.length > 0 ? (
            <div>
              <label className="block">
                <span className="font-medium">Note (optional)</span>
                <input
                  className="mt-1 w-full rounded border px-2 py-1"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                />
              </label>
              <div className="mt-2 flex gap-2">
                {options.map((s) => (
                  <button
                    key={s}
                    disabled={busy}
                    className="rounded border px-3 py-1 disabled:opacity-50"
                    onClick={() => changeStatus(s)}
                  >
                    Mark as {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-gray-600">
              {current === 'withdrawn' ? 'The applicant withdrew this application.' : 'This application is final.'}
            </p>
          )}
        </>
      )}
    </div>
  );
}

export default function ApplicantsPage() {
  const { id } = useParams<{ id: string }>();
  const { loading, allowed } = useIsOwnerRole();
  const [items, setItems] = useState<Item[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [openId, setOpenId] = useState('');
  const [error, setError] = useState('');
  const [title, setTitle] = useState('');

  const loadPage = useCallback(
    async (after: string | null) => {
      try {
        const page = await api<Page>(`/jobs/${id}/applications`, { query: { limit: 20, cursor: after } });
        setItems((cur) => (after ? [...(cur ?? []), ...page.items] : page.items));
        setCursor(page.next_cursor);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : 'Could not load applicants.');
      }
    },
    [id],
  );

  useEffect(() => {
    if (!allowed) return;
    loadPage(null);
    api<{ title: string }>(`/jobs/${id}`)
      .then((j) => setTitle(j.title))
      .catch(() => undefined);
  }, [allowed, id, loadPage]);

  if (loading) return <p className="text-sm text-gray-600">Loading...</p>;
  if (!allowed) return <NotAllowed />;

  return (
    <div>
      <Link href="/jobs" className="text-sm underline">
        Back to my vacancies
      </Link>
      <h1 className="mt-2 text-2xl font-semibold">Applicants{title ? `: ${title}` : ''}</h1>
      {error && <p className="mt-3 text-sm text-red-700">{error}</p>}
      {!items && !error && <p className="mt-3 text-sm text-gray-600">Loading...</p>}
      {items && items.length === 0 && <p className="mt-3 text-sm">Nobody has applied yet.</p>}
      {items && items.length > 0 && (
        <ul className="mt-3 divide-y rounded border">
          {items.map((it) => (
            <li key={it.id} className="p-3 text-sm">
              <p className="font-medium">{it.applicant?.full_name ?? 'Unknown applicant'}</p>
              {it.applicant && (
                <p className="text-gray-700">
                  {it.applicant.email} · {it.applicant.phone} · class of {it.applicant.angkatan}
                </p>
              )}
              {it.applicant && it.applicant.skills.length > 0 && (
                <p className="text-gray-500">{it.applicant.skills.map((s) => s.name).join(', ')}</p>
              )}
              <p className="text-gray-500">
                Status: {it.status} · Applied {it.created_at.slice(0, 10)}
              </p>
              <button className="mt-1 underline" onClick={() => setOpenId(openId === it.id ? '' : it.id)}>
                {openId === it.id ? 'Hide details' : 'Show details'}
              </button>
              {openId === it.id && (
                <ApplicantPanel
                  item={it}
                  onChanged={(status) =>
                    setItems((cur) => (cur ?? []).map((x) => (x.id === it.id ? { ...x, status } : x)))
                  }
                />
              )}
            </li>
          ))}
        </ul>
      )}
      {cursor && (
        <button className="mt-3 rounded border px-3 py-1 text-sm" onClick={() => loadPage(cursor)}>
          Show more
        </button>
      )}
    </div>
  );
}
