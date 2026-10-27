'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ArrowClockwise,
  ArrowLeft,
  CaretDown,
  DownloadSimple,
  Envelope,
  FilePdf,
  FileVideo,
  IdentificationCard,
  Phone,
} from '@phosphor-icons/react';
import { stagger } from '@/components/AuthShell';
import Chip from '@/components/Chip';
import { FormAlert, inputClass } from '@/components/FormField';
import { SECTION_LABEL } from '@/components/home/Band';
import { NotAllowed, useIsOwnerRole } from '@/components/OwnerGate';
import { BTN_DANGER, BTN_DANGER_OUTLINE, BTN_OUTLINE, BTN_PRIMARY, EASE, PageHeader, Pill } from '@/components/ui';
import { api, ApiError, buildUrl } from '@/lib/api';
import { initials } from '@/lib/labels';

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

const STATUS_LABEL: Record<string, string> = {
  submitted: 'Submitted',
  shortlisted: 'Shortlisted',
  accepted: 'Accepted',
  rejected: 'Rejected',
  withdrawn: 'Withdrawn',
};

const NEXT: Record<string, string[]> = {
  submitted: ['shortlisted', 'accepted', 'rejected'],
  shortlisted: ['accepted', 'rejected'],
  accepted: ['shortlisted', 'rejected'],
};

const ACTION_LABEL: Record<string, string> = {
  shortlisted: 'Shortlist',
  accepted: 'Accept',
  rejected: 'Reject',
};

function statusTone(status: string): 'solid' | 'outline' | 'muted' {
  return status === 'accepted' ? 'solid' : status === 'rejected' || status === 'withdrawn' ? 'muted' : 'outline';
}

function formatDate(value: string): string {
  return new Date(value.length === 10 ? value + 'T00:00:00' : value).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

function formatSize(n: number): string {
  if (n >= 1024 * 1024) return (n / (1024 * 1024)).toFixed(1) + ' MB';
  if (n >= 1024) return Math.round(n / 1024) + ' KB';
  return n + ' B';
}

function FileLink({
  href,
  icon: Icon,
  label,
  meta,
  missing,
}: {
  href: string;
  icon: React.ElementType;
  label: string;
  meta?: string;
  missing?: string;
}) {
  const body = (
    <>
      <span aria-hidden className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-zinc-100 text-zinc-700">
        <Icon size={20} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-medium text-zinc-900">{label}</span>
        <span className="block font-mono text-xs text-zinc-500">{missing ?? meta}</span>
      </span>
      {!missing && <DownloadSimple size={18} className="shrink-0 text-zinc-500" />}
    </>
  );
  if (missing) {
    return <li className="flex items-center gap-3 rounded-2xl border border-dashed border-zinc-200 px-4 py-3 opacity-70">{body}</li>;
  }
  return (
    <li>
      <a
        href={href}
        className={`flex items-center gap-3 rounded-2xl border border-zinc-200 bg-white px-4 py-3 transition duration-300 ${EASE} hover:border-zinc-400 active:scale-[0.99]`}
      >
        {body}
      </a>
    </li>
  );
}

function ApplicantPanel({ item, onChanged }: { item: Item; onChanged: (status: string) => void }) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [confirmReject, setConfirmReject] = useState(false);

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
      setConfirmReject(false);
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
  const history = detail ? [...detail.history].reverse() : [];

  return (
    <div className="mt-5 rounded-[2rem] border border-zinc-200/60 bg-white p-6 shadow-[0_20px_40px_-15px_rgba(24,24,27,0.08)] md:p-8">
      {error && (
        <div className="mb-5">
          <FormAlert>{error}</FormAlert>
        </div>
      )}

      {!detail && !error && (
        <div aria-hidden className="flex animate-pulse flex-col gap-4">
          <div className="h-5 w-48 rounded-full bg-zinc-200/70" />
          <div className="h-20 rounded-2xl bg-zinc-200/60" />
        </div>
      )}

      {detail && (
        <div className="grid gap-8 lg:grid-cols-2">
          {/* Left: what they wrote and where it stands */}
          <div className="flex flex-col gap-8">
            <section>
              <h3 className={SECTION_LABEL}>Cover note</h3>
              {detail.cover_note ? (
                <p className="mt-3 whitespace-pre-wrap leading-relaxed text-zinc-700">{detail.cover_note}</p>
              ) : (
                <p className="mt-3 text-zinc-500">No cover note.</p>
              )}
            </section>

            <section>
              <h3 className={SECTION_LABEL}>History</h3>
              <ol className="mt-4">
                {history.map((h, i) => (
                  <li key={i} className="relative flex gap-4 pb-5 last:pb-0">
                    {i < history.length - 1 && (
                      <span aria-hidden className="absolute left-[0.3125rem] top-4 h-[calc(100%-0.75rem)] w-px bg-zinc-200" />
                    )}
                    <span
                      aria-hidden
                      className={`relative mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${i === 0 ? 'bg-zinc-900' : 'border border-zinc-300 bg-white'}`}
                    />
                    <div className="min-w-0 text-sm">
                      <p className="font-medium text-zinc-900">{STATUS_LABEL[h.to_status] ?? h.to_status}</p>
                      <p className="font-mono text-xs text-zinc-500">{formatDate(h.created_at)}</p>
                      {h.note && <p className="mt-1.5 text-zinc-600">{h.note}</p>}
                    </div>
                  </li>
                ))}
              </ol>
            </section>
          </div>

          {/* Right: files, identity, decision */}
          <div className="flex flex-col gap-8">
            <section>
              <h3 className={SECTION_LABEL}>Files</h3>
              <ul className="mt-3 flex flex-col gap-2">
                <FileLink
                  href={buildUrl(`/applications/${item.id}/cv`)}
                  icon={FilePdf}
                  label="CV"
                  meta={item.documents.cv ? `${item.documents.cv.ext.replace(/^\./, '').toUpperCase()} · ${formatSize(item.documents.cv.size)}` : undefined}
                  missing={item.documents.cv ? undefined : 'Not attached'}
                />
                <FileLink
                  href={buildUrl(`/applications/${item.id}/video`)}
                  icon={FileVideo}
                  label="Intro video"
                  meta={item.documents.video ? `${item.documents.video.ext.replace(/^\./, '').toUpperCase()} · ${formatSize(item.documents.video.size)}` : undefined}
                  missing={item.documents.video ? undefined : 'Not attached'}
                />
                <FileLink
                  href={buildUrl(`/applications/${item.id}/identity/ktp`)}
                  icon={IdentificationCard}
                  label="ID card"
                  meta="Sensitive document"
                />
              </ul>
            </section>

            <section>
              <h3 className={SECTION_LABEL}>Identity data</h3>
              {!identity ? (
                <div className="mt-3">
                  <p className="text-sm text-zinc-500">National ID number, address and birth date are hidden until you ask.</p>
                  <button type="button" onClick={showIdentity} className={`${BTN_OUTLINE} mt-3`}>
                    Show identity data
                  </button>
                </div>
              ) : (
                <dl className="mt-3 divide-y divide-zinc-200 rounded-2xl border border-zinc-200 bg-white px-4 text-sm">
                  <div className="flex justify-between gap-4 py-3">
                    <dt className="text-zinc-500">National ID</dt>
                    <dd className="font-mono text-xs text-zinc-900">{identity.nik}</dd>
                  </div>
                  <div className="flex justify-between gap-4 py-3">
                    <dt className="text-zinc-500">Address</dt>
                    <dd className="text-right text-zinc-900">{identity.address}</dd>
                  </div>
                  <div className="flex justify-between gap-4 py-3">
                    <dt className="text-zinc-500">Birth date</dt>
                    <dd className="text-zinc-900">{formatDate(identity.birth_date)}</dd>
                  </div>
                  <div className="flex justify-between gap-4 py-3">
                    <dt className="text-zinc-500">ID card uploaded</dt>
                    <dd className="text-zinc-900">{identity.ktp_available ? 'Yes' : 'No'}</dd>
                  </div>
                </dl>
              )}
            </section>

            <section>
              <h3 className={SECTION_LABEL}>Decision</h3>
              {options.length > 0 ? (
                <div className="mt-3 flex flex-col gap-4">
                  <label className="flex flex-col gap-2 text-sm">
                    <span className="font-medium text-zinc-900">
                      Note to the applicant <span className="font-normal text-zinc-500">(optional)</span>
                    </span>
                    <input className={inputClass} value={note} onChange={(e) => setNote(e.target.value)} maxLength={600} />
                    <span className="text-right font-mono text-xs text-zinc-400">{note.length}/500</span>
                  </label>
                  <div className="flex flex-wrap gap-3">
                    {options.map((s) => {
                      if (s === 'rejected') {
                        return confirmReject ? (
                          <span key={s} className="flex flex-wrap items-center gap-2">
                            <button type="button" disabled={busy} onClick={() => changeStatus(s)} className={BTN_DANGER}>
                              {busy ? 'Saving...' : 'Confirm rejection'}
                            </button>
                            <button type="button" onClick={() => setConfirmReject(false)} className={BTN_OUTLINE}>
                              Cancel
                            </button>
                          </span>
                        ) : (
                          <button key={s} type="button" disabled={busy} onClick={() => setConfirmReject(true)} className={BTN_DANGER_OUTLINE}>
                            Reject
                          </button>
                        );
                      }
                      return (
                        <button
                          key={s}
                          type="button"
                          disabled={busy}
                          onClick={() => changeStatus(s)}
                          className={s === 'accepted' ? BTN_PRIMARY : BTN_OUTLINE}
                        >
                          {ACTION_LABEL[s]}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ) : (
                <p className="mt-3 text-sm text-zinc-500">
                  {current === 'withdrawn' ? 'The applicant withdrew this application.' : 'This application is final.'}
                </p>
              )}
            </section>
          </div>
        </div>
      )}
    </div>
  );
}

function ListSkeleton() {
  return (
    <ul aria-hidden className="mt-8 animate-pulse divide-y divide-zinc-200 border-y border-zinc-200">
      {[0, 1, 2].map((i) => (
        <li key={i} className="flex items-center gap-4 px-2 py-6">
          <div className="h-12 w-12 rounded-full bg-zinc-200/70" />
          <div className="flex flex-col gap-3">
            <div className="h-5 w-56 rounded-full bg-zinc-200/70" />
            <div className="h-4 w-72 max-w-full rounded-full bg-zinc-200/70" />
          </div>
        </li>
      ))}
    </ul>
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
  const [filter, setFilter] = useState('all');
  const [more, setMore] = useState(false);

  const loadPage = useCallback(
    async (after: string | null) => {
      setError('');
      setMore(true);
      try {
        const page = await api<Page>(`/jobs/${id}/applications`, { query: { limit: 20, cursor: after } });
        setItems((cur) => (after ? [...(cur ?? []), ...page.items] : page.items));
        setCursor(page.next_cursor);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : 'Could not load applicants.');
      } finally {
        setMore(false);
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

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const it of items ?? []) c[it.status] = (c[it.status] ?? 0) + 1;
    return c;
  }, [items]);

  if (loading) {
    return (
      <div className="py-4">
        <div aria-hidden className="flex animate-pulse flex-col gap-5">
          <div className="h-4 w-24 rounded-full bg-zinc-200/70" />
          <div className="h-12 w-80 max-w-full rounded-full bg-zinc-200/70" />
        </div>
        <ListSkeleton />
      </div>
    );
  }
  if (!allowed) return <NotAllowed />;

  const present = Object.keys(STATUS_LABEL).filter((s) => counts[s]);
  const visible = (items ?? []).filter((it) => filter === 'all' || it.status === filter);

  return (
    <div className="py-4">
      <Link
        href="/jobs"
        className="mb-6 inline-flex items-center gap-1.5 text-sm font-medium text-zinc-600 transition-colors hover:text-zinc-900"
      >
        <ArrowLeft size={14} weight="bold" />
        My vacancies
      </Link>
      <PageHeader
        eyebrow="Applicants"
        title={title || 'Applicants'}
        subtitle="Review each application, download the files they sent, and decide."
      />

      {error && (
        <div className="mt-10 flex flex-col items-start gap-3">
          <FormAlert>{error}</FormAlert>
          <button type="button" onClick={() => loadPage(null)} className={BTN_OUTLINE}>
            <ArrowClockwise size={16} />
            Try again
          </button>
        </div>
      )}

      {!items && !error && <ListSkeleton />}

      {items && items.length === 0 && (
        <p className="rise mt-10 rounded-[2rem] border border-dashed border-zinc-300 px-8 py-12 text-zinc-500" style={stagger(1)}>
          Nobody has applied yet. Applications show up here as soon as students send them.
        </p>
      )}

      {items && items.length > 0 && (
        <>
          <div className="rise mt-10 flex flex-wrap gap-2" role="group" aria-label="Filter by status" style={stagger(1)}>
            <Chip selected={filter === 'all'} onClick={() => setFilter('all')}>
              All <span className="ml-1 font-mono text-xs opacity-70">{items.length}</span>
            </Chip>
            {present.map((s) => (
              <Chip key={s} selected={filter === s} onClick={() => setFilter(filter === s ? 'all' : s)}>
                {STATUS_LABEL[s]} <span className="ml-1 font-mono text-xs opacity-70">{counts[s]}</span>
              </Chip>
            ))}
          </div>

          <ul className="rise mt-6 divide-y divide-zinc-200 border-y border-zinc-200" style={stagger(2)}>
            {visible.map((it) => {
              const open = openId === it.id;
              const a = it.applicant;
              const shown = a?.skills.slice(0, 4) ?? [];
              const extra = (a?.skills.length ?? 0) - shown.length;
              return (
                <li key={it.id} className="px-2 py-6">
                  <div className="flex flex-wrap items-start gap-x-5 gap-y-4">
                    <span
                      aria-hidden
                      className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-zinc-900 text-sm font-semibold text-zinc-50"
                    >
                      {initials(a?.full_name)}
                    </span>

                    <div className="min-w-0 flex-1 basis-64">
                      <p className="flex flex-wrap items-center gap-3 text-xl font-semibold tracking-tight text-zinc-900">
                        {a?.full_name ?? 'Unknown applicant'}
                        <Pill tone={statusTone(it.status)}>{STATUS_LABEL[it.status] ?? it.status}</Pill>
                      </p>
                      {a && (
                        <p className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-zinc-500">
                          <span className="inline-flex items-center gap-1.5">
                            <Envelope size={14} />
                            {a.email}
                          </span>
                          <span className="inline-flex items-center gap-1.5">
                            <Phone size={14} />
                            {a.phone}
                          </span>
                          <span>Class of {a.angkatan}</span>
                        </p>
                      )}
                      {shown.length > 0 && (
                        <ul className="mt-3 flex flex-wrap gap-2" aria-label="Skills">
                          {shown.map((s) => (
                            <li key={s.id} className="rounded-full bg-zinc-100 px-3 py-1 text-xs text-zinc-700">
                              {s.name}
                            </li>
                          ))}
                          {extra > 0 && <li className="rounded-full px-2 py-1 text-xs text-zinc-500">+{extra} more</li>}
                        </ul>
                      )}
                    </div>

                    <div className="flex items-center gap-4">
                      <span className="font-mono text-xs text-zinc-500">Applied {formatDate(it.created_at)}</span>
                      <button
                        type="button"
                        aria-expanded={open}
                        aria-controls={`panel-${it.id}`}
                        onClick={() => setOpenId(open ? '' : it.id)}
                        className={`inline-flex min-h-10 items-center gap-1.5 rounded-full border px-4 text-sm font-medium transition duration-300 ${EASE} active:scale-[0.98] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900 ${open ? 'border-zinc-900 bg-zinc-900 text-zinc-50' : 'border-zinc-200 bg-white text-zinc-900 hover:border-zinc-400'
                          }`}
                      >
                        {open ? 'Hide' : 'Review'}
                        <CaretDown size={14} weight="bold" className={`transition-transform duration-300 ${EASE} ${open ? 'rotate-180' : ''}`} />
                      </button>
                    </div>
                  </div>

                  {open && (
                    <div id={`panel-${it.id}`}>
                      <ApplicantPanel
                        item={it}
                        onChanged={(status) =>
                          setItems((cur) => (cur ?? []).map((x) => (x.id === it.id ? { ...x, status } : x)))
                        }
                      />
                    </div>
                  )}
                </li>
              );
            })}
            {visible.length === 0 && <li className="px-2 py-10 text-zinc-500">No applications with this status.</li>}
          </ul>
        </>
      )}

      {cursor && (
        <button type="button" disabled={more} className={`${BTN_OUTLINE} mt-6`} onClick={() => loadPage(cursor)}>
          {more ? 'Loading...' : 'Show more'}
        </button>
      )}
    </div>
  );
}