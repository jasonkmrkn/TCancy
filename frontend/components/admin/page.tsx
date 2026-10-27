'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowClockwise, Check, MagnifyingGlass, Quotes, ShieldCheck, X } from '@phosphor-icons/react';
import BenchmarksTab from '@/components/admin/BenchmarksTab';
import Chip from '@/components/Chip';
import FormField, { FormAlert, inputClass, textareaClass } from '@/components/FormField';
import { SECTION_LABEL } from '@/components/home/Band';
import { ApiError, messageFor } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import {
    admin,
    type AdminAlumni,
    type AdminOverview,
    type AdminTestimonial,
    type AdminUser,
    type AlumniState,
    type Page,
    type Role,
    type AccountStatus,
    type TestimonialStatus,
} from '@/lib/endpoints';
import { initials } from '@/lib/labels';

/* ------------------------------------------------------------------ */
/* Shared bits                                                         */
/* ------------------------------------------------------------------ */

type Tab = 'overview' | 'alumni' | 'testimonials' | 'users' | 'benchmarks';

const TABS: { key: Tab; label: string }[] = [
    { key: 'overview', label: 'Overview' },
    { key: 'alumni', label: 'Alumni verification' },
    { key: 'testimonials', label: 'Testimonials' },
    { key: 'users', label: 'Users' },
    { key: 'benchmarks', label: 'Benchmarks' },
];

const EASE = 'ease-[cubic-bezier(0.16,1,0.3,1)]';
const BTN_BASE = `inline-flex min-h-11 items-center justify-center gap-2 rounded-full px-5 text-sm font-medium transition duration-300 ${EASE} active:translate-y-[1px] active:scale-[0.98] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900 disabled:cursor-not-allowed disabled:opacity-50`;
const BTN_PRIMARY = `${BTN_BASE} bg-zinc-900 text-zinc-50 shadow-[inset_0_1px_0_rgba(255,255,255,0.12)] hover:bg-zinc-800`;
const BTN_OUTLINE = `${BTN_BASE} border border-zinc-200 bg-white text-zinc-900 hover:border-zinc-400`;

const cap = (s: string) => {
    const t = s.replace(/_/g, ' ');
    return t.charAt(0).toUpperCase() + t.slice(1);
};

function errText(e: unknown, fallback: string): string {
    return e instanceof ApiError ? messageFor(e.code, e.message) : fallback;
}

function formatDate(value: string | null): string {
    if (!value) return 'Never';
    return new Date(value).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

function Badge({ tone = 'outline', children }: { tone?: 'solid' | 'outline' | 'muted'; children: React.ReactNode }) {
    const style =
        tone === 'solid'
            ? 'bg-zinc-900 text-zinc-50'
            : tone === 'muted'
                ? 'bg-zinc-200/70 text-zinc-600'
                : 'border border-zinc-300 text-zinc-700';
    return <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium uppercase tracking-wider ${style}`}>{children}</span>;
}

function SkeletonRows({ n = 3 }: { n?: number }) {
    return (
        <ul aria-hidden className="mt-6 flex animate-pulse flex-col gap-3">
            {Array.from({ length: n }).map((_, i) => (
                <li key={i} className="h-24 rounded-[2rem] bg-zinc-200/60" />
            ))}
        </ul>
    );
}

function ErrorBox({ message, onRetry }: { message: string; onRetry: () => void }) {
    return (
        <div className="mt-6 flex flex-col items-start gap-3">
            <FormAlert>{message}</FormAlert>
            <button type="button" onClick={onRetry} className={BTN_OUTLINE}>
                <ArrowClockwise size={16} weight="regular" />
                Try again
            </button>
        </div>
    );
}

function Empty({ children }: { children: React.ReactNode }) {
    return (
        <p className="mt-6 rounded-[2rem] border border-dashed border-zinc-300 px-6 py-10 text-center text-sm text-zinc-500">
            {children}
        </p>
    );
}

function Notice({ message }: { message: string }) {
    return (
        <div role="status" aria-live="polite">
            {message && (
                <p className="mt-6 flex items-center gap-2 rounded-full bg-zinc-100 px-5 py-3 text-sm text-zinc-700">
                    <Check size={16} weight="bold" className="shrink-0" />
                    {message}
                </p>
            )}
        </div>
    );
}

function MoreButton({ cursor, busy, onClick }: { cursor: string | null; busy: boolean; onClick: () => void }) {
    if (!cursor) return null;
    return (
        <div className="mt-6">
            <button type="button" onClick={onClick} disabled={busy} className={BTN_OUTLINE}>
                {busy ? 'Loading...' : 'Show more'}
            </button>
        </div>
    );
}

function Filters({ label, children }: { label: string; children: React.ReactNode }) {
    return (
        <div role="group" aria-label={label} className="flex flex-wrap gap-2">
            {children}
        </div>
    );
}

/** Cursor-paginated list with stale-response protection. `listKey` restarts the list when filters change. */
function useList<T>(fetcher: (cursor: string | null) => Promise<Page<T>>, listKey: string) {
    const [items, setItems] = useState<T[] | null>(null);
    const [cursor, setCursor] = useState<string | null>(null);
    const [error, setError] = useState('');
    const [busyMore, setBusyMore] = useState(false);
    const fetcherRef = useRef(fetcher);
    fetcherRef.current = fetcher;
    const seq = useRef(0);

    const load = useCallback(async (after: string | null) => {
        const id = ++seq.current;
        setError('');
        if (after) setBusyMore(true);
        try {
            const res = await fetcherRef.current(after);
            if (id !== seq.current) return;
            setItems((old) => (after && old ? [...old, ...res.items] : res.items));
            setCursor(res.next_cursor);
        } catch (e) {
            if (id !== seq.current) return;
            setError(errText(e, 'Could not load the list.'));
        } finally {
            if (id === seq.current) setBusyMore(false);
        }
    }, []);

    useEffect(() => {
        setItems(null);
        setCursor(null);
        load(null);
    }, [listKey, load]);

    return { items, setItems, cursor, error, busyMore, more: () => load(cursor), reload: () => load(null) };
}

/* ------------------------------------------------------------------ */
/* Overview                                                            */
/* ------------------------------------------------------------------ */

function StatGroup({ title, counts }: { title: string; counts: Record<string, number> }) {
    return (
        <section>
            <h3 className={SECTION_LABEL}>{title}</h3>
            <ul className="mt-5 divide-y divide-zinc-200 border-y border-zinc-200">
                {Object.entries(counts).map(([k, v]) => (
                    <li key={k} className="flex items-center justify-between py-4 text-[15px] text-zinc-800">
                        <span>{cap(k)}</span>
                        <span className="font-mono text-sm font-semibold tabular-nums text-zinc-900">{v}</span>
                    </li>
                ))}
            </ul>
        </section>
    );
}

function OverviewTab({ onReview }: { onReview: () => void }) {
    const [data, setData] = useState<AdminOverview | null>(null);
    const [error, setError] = useState('');

    const load = useCallback(() => {
        setError('');
        admin
            .overview()
            .then(setData)
            .catch((e) => setError(errText(e, 'Could not load the overview.')));
    }, []);

    useEffect(load, [load]);

    if (error) return <ErrorBox message={error} onRetry={load} />;
    if (!data) {
        return (
            <div aria-hidden className="mt-8 flex animate-pulse flex-col gap-8">
                <div className="h-16 rounded-full bg-zinc-200/60" />
                <div className="grid gap-12 md:grid-cols-3">
                    {[0, 1, 2].map((i) => (
                        <div key={i} className="h-56 rounded-[2rem] bg-zinc-200/60" />
                    ))}
                </div>
            </div>
        );
    }

    const waiting = data.alumni_awaiting_decision;
    return (
        <div className="mt-8">
            <div className="flex flex-wrap items-center justify-between gap-4 rounded-[2rem] bg-zinc-100 px-8 py-5 md:rounded-full">
                <p className="text-[15px] text-zinc-800">
                    Alumni awaiting a decision: <strong className="font-mono font-semibold">{waiting}</strong>
                </p>
                {waiting > 0 && (
                    <button type="button" onClick={onReview} className={BTN_PRIMARY}>
                        Review applications
                    </button>
                )}
            </div>

            <div className="mt-12 grid gap-x-12 gap-y-14 md:grid-cols-2 lg:grid-cols-3">
                <StatGroup title="Users by role" counts={data.users_by_role} />
                <StatGroup title="Users by status" counts={data.users_by_status} />
                <StatGroup title="Vacancies" counts={data.jobs_by_status} />
                <StatGroup title="Applications" counts={data.applications_by_status} />
                <StatGroup title="Documents" counts={data.documents_by_type} />
            </div>
        </div>
    );
}

/* ------------------------------------------------------------------ */
/* Alumni verification                                                 */
/* ------------------------------------------------------------------ */

const ALUMNI_STATES: { key: AlumniState; label: string }[] = [
    { key: 'pending', label: 'Pending' },
    { key: 'approved', label: 'Approved' },
    { key: 'rejected', label: 'Rejected' },
];

function AlumniTab() {
    const [state, setState] = useState<AlumniState>('pending');
    const list = useList<AdminAlumni>((c) => admin.alumni({ state, limit: 20, cursor: c }), state);
    const [busyId, setBusyId] = useState('');
    const [rejectId, setRejectId] = useState('');
    const [reason, setReason] = useState('');
    const [notice, setNotice] = useState('');
    const [actionError, setActionError] = useState('');

    function remove(id: string) {
        list.setItems((old) => (old ?? []).filter((a) => a.id !== id));
    }

    async function approve(a: AdminAlumni) {
        setBusyId(a.id);
        setActionError('');
        setNotice('');
        try {
            await admin.approveAlumni(a.id);
            remove(a.id);
            setNotice(`Approved @${a.username}. They can now post vacancies.`);
        } catch (e) {
            setActionError(errText(e, 'Could not approve this account.'));
        } finally {
            setBusyId('');
        }
    }

    async function reject(a: AdminAlumni) {
        setBusyId(a.id);
        setActionError('');
        setNotice('');
        try {
            await admin.rejectAlumni(a.id, reason.trim());
            remove(a.id);
            setRejectId('');
            setReason('');
            setNotice(`Rejected @${a.username}.`);
        } catch (e) {
            setActionError(errText(e, 'Could not reject this account.'));
        } finally {
            setBusyId('');
        }
    }

    return (
        <div className="mt-8">
            <Filters label="Verification state">
                {ALUMNI_STATES.map((s) => (
                    <Chip
                        key={s.key}
                        selected={state === s.key}
                        onClick={() => {
                            setState(s.key);
                            setRejectId('');
                            setNotice('');
                            setActionError('');
                        }}
                    >
                        {s.label}
                    </Chip>
                ))}
            </Filters>

            <Notice message={notice} />
            {actionError && (
                <div className="mt-6">
                    <FormAlert>{actionError}</FormAlert>
                </div>
            )}

            {list.error && <ErrorBox message={list.error} onRetry={list.reload} />}
            {!list.items && !list.error && <SkeletonRows />}
            {list.items && list.items.length === 0 && (
                <Empty>{state === 'pending' ? 'No alumni are waiting for a decision.' : `No ${state} alumni.`}</Empty>
            )}

            {list.items && list.items.length > 0 && (
                <ul className="mt-6 flex flex-col gap-3">
                    {list.items.map((a) => {
                        const open = rejectId === a.id;
                        const busy = busyId === a.id;
                        return (
                            <li
                                key={a.id}
                                className="rounded-[2rem] border border-zinc-200/70 bg-white p-6 shadow-[0_20px_40px_-15px_rgba(24,24,27,0.06)]"
                            >
                                <div className="flex flex-wrap items-start justify-between gap-4">
                                    <div className="flex min-w-0 items-start gap-4">
                                        <span
                                            aria-hidden
                                            className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-zinc-200/70 text-sm font-semibold text-zinc-700"
                                        >
                                            {initials(a.full_name ?? a.username)}
                                        </span>
                                        <div className="min-w-0">
                                            <p className="flex flex-wrap items-baseline gap-x-2 text-lg font-semibold tracking-tight text-zinc-900">
                                                {a.full_name || 'No name yet'}
                                                <span className="font-mono text-xs font-normal text-zinc-500">@{a.username}</span>
                                            </p>
                                            <p className="mt-1 text-sm text-zinc-600">
                                                {a.company || 'No company yet'} · Class of {a.angkatan ?? 'unknown'}
                                            </p>
                                            <p className="mt-1 font-mono text-xs text-zinc-500">Registered {formatDate(a.created_at)}</p>
                                        </div>
                                    </div>
                                    <div className="flex flex-wrap gap-2">
                                        <Badge tone={a.profile_complete ? 'outline' : 'muted'}>
                                            {a.profile_complete ? 'Profile complete' : 'Profile incomplete'}
                                        </Badge>
                                        <Badge tone={a.account_status === 'active' ? 'solid' : 'outline'}>{cap(a.account_status)}</Badge>
                                    </div>
                                </div>

                                {a.verification.reason && (
                                    <p className="mt-4 rounded-2xl bg-zinc-100 px-4 py-3 text-sm text-zinc-700">
                                        <span className="font-medium text-zinc-900">Rejection reason: </span>
                                        {a.verification.reason}
                                    </p>
                                )}

                                {state === 'pending' && (
                                    <div className="mt-5 border-t border-zinc-200 pt-5">
                                        {!a.profile_complete && (
                                            <p className="mb-4 text-sm text-zinc-500">
                                                This profile is incomplete, so it cannot be approved yet. Ask them to add their name, company and class year.
                                            </p>
                                        )}
                                        <div className="flex flex-wrap gap-3">
                                            <button
                                                type="button"
                                                disabled={busy || !a.profile_complete}
                                                onClick={() => approve(a)}
                                                className={BTN_PRIMARY}
                                            >
                                                <Check size={16} weight="bold" />
                                                {busy && !open ? 'Approving...' : 'Approve'}
                                            </button>
                                            <button
                                                type="button"
                                                disabled={busy}
                                                aria-expanded={open}
                                                onClick={() => {
                                                    setRejectId(open ? '' : a.id);
                                                    setReason('');
                                                }}
                                                className={BTN_OUTLINE}
                                            >
                                                <X size={16} weight="bold" />
                                                Reject
                                            </button>
                                        </div>

                                        {open && (
                                            <div className="mt-5 flex max-w-xl flex-col gap-4">
                                                <FormField label="Reason for rejection" hint={`${reason.length} of 500 characters. The alumnus will see this.`}>
                                                    <textarea
                                                        className={textareaClass}
                                                        value={reason}
                                                        onChange={(e) => setReason(e.target.value)}
                                                        maxLength={500}
                                                        rows={3}
                                                        autoFocus
                                                    />
                                                </FormField>
                                                <div>
                                                    <button type="button" disabled={busy || !reason.trim()} onClick={() => reject(a)} className={BTN_PRIMARY}>
                                                        {busy ? 'Rejecting...' : 'Confirm rejection'}
                                                    </button>
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                )}
                            </li>
                        );
                    })}
                </ul>
            )}
            <MoreButton cursor={list.cursor} busy={list.busyMore} onClick={list.more} />
        </div>
    );
}

/* ------------------------------------------------------------------ */
/* Testimonials                                                        */
/* ------------------------------------------------------------------ */

const TESTIMONIAL_STATES: { key: TestimonialStatus; label: string }[] = [
    { key: 'pending', label: 'Pending' },
    { key: 'approved', label: 'Approved' },
    { key: 'hidden', label: 'Hidden' },
];

function TestimonialsTab() {
    const [status, setStatus] = useState<TestimonialStatus>('pending');
    const list = useList<AdminTestimonial>((c) => admin.testimonials({ status, limit: 20, cursor: c }), status);
    const [busyId, setBusyId] = useState('');
    const [actionError, setActionError] = useState('');

    async function moderate(id: string, next: 'approved' | 'hidden') {
        setBusyId(id);
        setActionError('');
        try {
            await admin.moderateTestimonial(id, next);
            list.setItems((old) => (old ?? []).filter((t) => t.id !== id));
        } catch (e) {
            setActionError(errText(e, 'Could not update the testimonial.'));
        } finally {
            setBusyId('');
        }
    }

    return (
        <div className="mt-8">
            <Filters label="Testimonial status">
                {TESTIMONIAL_STATES.map((s) => (
                    <Chip
                        key={s.key}
                        selected={status === s.key}
                        onClick={() => {
                            setStatus(s.key);
                            setActionError('');
                        }}
                    >
                        {s.label}
                    </Chip>
                ))}
            </Filters>

            {actionError && (
                <div className="mt-6">
                    <FormAlert>{actionError}</FormAlert>
                </div>
            )}
            {list.error && <ErrorBox message={list.error} onRetry={list.reload} />}
            {!list.items && !list.error && <SkeletonRows />}
            {list.items && list.items.length === 0 && <Empty>No {status} testimonials.</Empty>}

            {list.items && list.items.length > 0 && (
                <ul className="mt-6 flex flex-col gap-3">
                    {list.items.map((t) => (
                        <li
                            key={t.id}
                            className="rounded-[2rem] border border-zinc-200/70 bg-white p-6 shadow-[0_20px_40px_-15px_rgba(24,24,27,0.06)]"
                        >
                            <Quotes size={22} weight="regular" className="text-zinc-400" />
                            <p className="mt-3 max-w-[70ch] whitespace-pre-wrap leading-relaxed text-zinc-800">{t.content}</p>
                            <p className="mt-4 text-sm text-zinc-500">
                                {t.display_first_name || 'Anonymous'}
                                {t.display_company ? `, ${t.display_company}` : ''} · {t.show_name ? 'Name shown publicly' : 'Name hidden'} ·{' '}
                                <span className="font-mono text-xs">{formatDate(t.created_at)}</span>
                            </p>
                            <div className="mt-5 flex flex-wrap gap-3 border-t border-zinc-200 pt-5">
                                {status !== 'approved' && (
                                    <button type="button" disabled={busyId === t.id} onClick={() => moderate(t.id, 'approved')} className={BTN_PRIMARY}>
                                        <Check size={16} weight="bold" />
                                        Approve
                                    </button>
                                )}
                                {status !== 'hidden' && (
                                    <button type="button" disabled={busyId === t.id} onClick={() => moderate(t.id, 'hidden')} className={BTN_OUTLINE}>
                                        Hide
                                    </button>
                                )}
                            </div>
                        </li>
                    ))}
                </ul>
            )}
            <MoreButton cursor={list.cursor} busy={list.busyMore} onClick={list.more} />
        </div>
    );
}

/* ------------------------------------------------------------------ */
/* Users                                                               */
/* ------------------------------------------------------------------ */

const ROLE_FILTERS: { key: Role | ''; label: string }[] = [
    { key: '', label: 'All roles' },
    { key: 'applicant', label: 'Applicant' },
    { key: 'alumni', label: 'Alumni' },
    { key: 'admin', label: 'Admin' },
];

const STATUS_FILTERS: { key: AccountStatus | ''; label: string }[] = [
    { key: '', label: 'Any status' },
    { key: 'active', label: 'Active' },
    { key: 'pending', label: 'Pending' },
    { key: 'suspended', label: 'Suspended' },
];

function UsersTab() {
    const [role, setRole] = useState<Role | ''>('');
    const [status, setStatus] = useState<AccountStatus | ''>('');
    const [qInput, setQInput] = useState('');
    const [q, setQ] = useState('');
    const [busyId, setBusyId] = useState('');
    const [confirmId, setConfirmId] = useState('');
    const [actionError, setActionError] = useState('');

    useEffect(() => {
        const t = setTimeout(() => setQ(qInput.trim()), 300);
        return () => clearTimeout(t);
    }, [qInput]);

    const list = useList<AdminUser>(
        (c) => admin.users({ role: role || undefined, status: status || undefined, q: q || undefined, limit: 20, cursor: c }),
        `${role}|${status}|${q}`,
    );

    async function setUserStatus(u: AdminUser, next: 'active' | 'suspended') {
        setBusyId(u.id);
        setActionError('');
        try {
            const updated = await admin.setUserStatus(u.id, next);
            list.setItems((old) => (old ?? []).map((x) => (x.id === u.id ? { ...x, status: updated.status } : x)));
            setConfirmId('');
        } catch (e) {
            setActionError(errText(e, 'Could not change the status.'));
        } finally {
            setBusyId('');
        }
    }

    return (
        <div className="mt-8">
            <div className="relative max-w-md">
                <MagnifyingGlass
                    size={18}
                    weight="regular"
                    aria-hidden
                    className="pointer-events-none absolute left-5 top-1/2 -translate-y-1/2 text-zinc-400"
                />
                <input
                    type="search"
                    aria-label="Search by username"
                    placeholder="Search by username"
                    value={qInput}
                    onChange={(e) => setQInput(e.target.value)}
                    maxLength={64}
                    className={`${inputClass} pl-12`}
                />
            </div>
            <div className="mt-4 flex flex-col gap-3">
                <Filters label="Role">
                    {ROLE_FILTERS.map((r) => (
                        <Chip key={r.key || 'all'} selected={role === r.key} onClick={() => setRole(r.key)}>
                            {r.label}
                        </Chip>
                    ))}
                </Filters>
                <Filters label="Status">
                    {STATUS_FILTERS.map((s) => (
                        <Chip key={s.key || 'any'} selected={status === s.key} onClick={() => setStatus(s.key)}>
                            {s.label}
                        </Chip>
                    ))}
                </Filters>
            </div>

            {actionError && (
                <div className="mt-6">
                    <FormAlert>{actionError}</FormAlert>
                </div>
            )}
            {list.error && <ErrorBox message={list.error} onRetry={list.reload} />}
            {!list.items && !list.error && <SkeletonRows n={4} />}
            {list.items && list.items.length === 0 && <Empty>No users match these filters.</Empty>}

            {list.items && list.items.length > 0 && (
                <ul className="mt-6 divide-y divide-zinc-200 border-y border-zinc-200">
                    {list.items.map((u) => {
                        const suspended = u.status === 'suspended';
                        const confirming = confirmId === u.id;
                        return (
                            <li key={u.id} className="flex flex-wrap items-center justify-between gap-4 py-5">
                                <div className="flex min-w-0 items-center gap-4">
                                    <span
                                        aria-hidden
                                        className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-zinc-200/70 text-sm font-semibold text-zinc-700"
                                    >
                                        {initials(u.username)}
                                    </span>
                                    <div className="min-w-0">
                                        <p className="flex flex-wrap items-center gap-2 font-medium text-zinc-900">
                                            {u.username}
                                            <Badge tone="outline">{cap(u.role)}</Badge>
                                            <Badge tone={u.status === 'active' ? 'solid' : u.status === 'pending' ? 'outline' : 'muted'}>
                                                {cap(u.status)}
                                            </Badge>
                                        </p>
                                        <p className="mt-1 font-mono text-xs text-zinc-500">
                                            Joined {formatDate(u.created_at)} · Last login {formatDate(u.last_login_at)}
                                        </p>
                                    </div>
                                </div>

                                {u.role !== 'admin' &&
                                    (confirming ? (
                                        <div className="flex flex-wrap items-center gap-2">
                                            <span className="text-sm text-zinc-600">Suspend this account?</span>
                                            <button type="button" disabled={busyId === u.id} onClick={() => setUserStatus(u, 'suspended')} className={BTN_PRIMARY}>
                                                Confirm
                                            </button>
                                            <button type="button" onClick={() => setConfirmId('')} className={BTN_OUTLINE}>
                                                Cancel
                                            </button>
                                        </div>
                                    ) : (
                                        <button
                                            type="button"
                                            disabled={busyId === u.id}
                                            onClick={() => (suspended ? setUserStatus(u, 'active') : setConfirmId(u.id))}
                                            className={BTN_OUTLINE}
                                        >
                                            {suspended ? 'Reactivate' : 'Suspend'}
                                        </button>
                                    ))}
                            </li>
                        );
                    })}
                </ul>
            )}
            <MoreButton cursor={list.cursor} busy={list.busyMore} onClick={list.more} />
        </div>
    );
}

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

export default function AdminPage() {
    const { user, loading } = useAuth();
    const [tab, setTab] = useState<Tab>('overview');

    if (loading) {
        return (
            <div aria-hidden className="flex animate-pulse flex-col gap-6 py-4">
                <div className="h-4 w-24 rounded-full bg-zinc-200/70" />
                <div className="h-14 w-72 rounded-full bg-zinc-200/70" />
                <div className="h-16 rounded-full bg-zinc-200/70" />
            </div>
        );
    }

    if (!user || user.role !== 'admin' || user.status !== 'active') {
        return (
            <div className="py-4">
                <h1 className="text-3xl font-semibold tracking-tight text-zinc-900">Admin panel</h1>
                <p className="mt-3 text-zinc-500">
                    Only administrators can open this page.{' '}
                    {!user && (
                        <Link href="/login" className="font-medium text-zinc-900 underline underline-offset-4">
                            Sign in
                        </Link>
                    )}
                </p>
            </div>
        );
    }

    return (
        <div className="py-4">
            <header>
                <p className={`flex items-center gap-2 ${SECTION_LABEL} !text-zinc-900`}>
                    <ShieldCheck size={18} weight="regular" />
                    Admin
                </p>
                <h1 className="mt-4 text-5xl font-semibold leading-[1.05] tracking-tighter text-zinc-900 md:text-6xl">Admin panel</h1>
                <p className="mt-4 max-w-[60ch] text-lg text-zinc-500">
                    Review alumni, moderate testimonials and manage accounts.
                </p>
            </header>

            <div className="mt-10 overflow-x-auto">
                <div role="tablist" aria-label="Admin sections" className="inline-flex min-w-full gap-1 rounded-full bg-zinc-100 p-1.5">
                    {TABS.map((t) => {
                        const active = tab === t.key;
                        return (
                            <button
                                key={t.key}
                                role="tab"
                                id={`tab-${t.key}`}
                                aria-selected={active}
                                aria-controls={`panel-${t.key}`}
                                type="button"
                                onClick={() => setTab(t.key)}
                                className={`min-h-12 whitespace-nowrap rounded-full px-6 text-[15px] font-medium transition duration-300 ${EASE} focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900 ${active
                                        ? 'bg-white text-zinc-900 shadow-[0_2px_8px_-2px_rgba(24,24,27,0.12)]'
                                        : 'text-zinc-500 hover:text-zinc-800'
                                    }`}
                            >
                                {t.label}
                            </button>
                        );
                    })}
                </div>
            </div>

            <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
                {tab === 'overview' && <OverviewTab onReview={() => setTab('alumni')} />}
                {tab === 'alumni' && <AlumniTab />}
                {tab === 'testimonials' && <TestimonialsTab />}
                {tab === 'users' && <UsersTab />}
                {tab === 'benchmarks' && <BenchmarksTab />}
            </div>
        </div>
    );
}