'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { Check, Trash } from '@phosphor-icons/react';
import { stagger } from '@/components/AuthShell';
import { FormAlert, textareaClass } from '@/components/FormField';
import { SECTION_LABEL } from '@/components/home/Band';
import {
    BTN_DANGER,
    BTN_OUTLINE,
    BTN_PRIMARY,
    CARD,
    EASE,
    PageHeader,
    PageSkeleton,
    Pill,
    SignInNotice,
} from '@/components/ui';
import { ApiError, messageFor } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import {
    applications,
    testimonials,
    type ApplicationSummary,
    type OwnTestimonial,
    type TestimonialStatus,
} from '@/lib/endpoints';

const MIN = 20;
const MAX = 1000;

const STATUS: Record<TestimonialStatus, { label: string; tone: 'solid' | 'outline' | 'muted'; hint: string }> = {
    pending: { label: 'In review', tone: 'outline', hint: 'An admin will check it before it is shown on the home page.' },
    approved: { label: 'Published', tone: 'solid', hint: 'Visible on the home page.' },
    hidden: { label: 'Hidden', tone: 'muted', hint: 'An admin hid it. Only you can see it.' },
};

const formatDate = (v: string) =>
    new Date(v).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });

function errText(e: unknown, fallback: string): string {
    return e instanceof ApiError ? messageFor(e.code, e.message) : fallback;
}

export default function TestimonialsPage() {
    const { user, loading } = useAuth();
    const allowed = user?.role === 'applicant' && user.status === 'active';

    const [apps, setApps] = useState<ApplicationSummary[]>([]);
    const [mine, setMine] = useState<OwnTestimonial[]>([]);
    const [loaded, setLoaded] = useState(false);
    const [loadError, setLoadError] = useState('');

    const [appId, setAppId] = useState('');
    const [content, setContent] = useState('');
    const [showName, setShowName] = useState(true);
    const [errors, setErrors] = useState<Record<string, string>>({});
    const [error, setError] = useState('');
    const [notice, setNotice] = useState('');
    const [busy, setBusy] = useState(false);
    const [confirmId, setConfirmId] = useState<string | null>(null);
    const [deletingId, setDeletingId] = useState<string | null>(null);

    const load = useCallback(async () => {
        setLoadError('');
        try {
            const [a, t] = await Promise.all([applications.mine(), testimonials.mine()]);
            setApps(a);
            setMine(t.items);
        } catch (e) {
            setLoadError(errText(e, 'Could not load your testimonials.'));
        } finally {
            setLoaded(true);
        }
    }, []);

    useEffect(() => {
        if (allowed) load();
    }, [allowed, load]);

    const written = new Set(mine.map((t) => t.application_id));
    const eligible = apps.filter((a) => a.status === 'accepted' && !written.has(a.id));
    const accepted = apps.filter((a) => a.status === 'accepted');
    const jobOf = (id: string) => apps.find((a) => a.id === id)?.job;

    // Keep a valid selection: with a single option there is nothing to choose.
    useEffect(() => {
        if (eligible.length === 1) setAppId(eligible[0].id);
        else if (appId && !eligible.some((a) => a.id === appId)) setAppId('');
    }, [eligible, appId]);

    async function send(e: React.FormEvent) {
        e.preventDefault();
        setError('');
        setNotice('');
        const errs: Record<string, string> = {};
        const len = content.trim().length;
        if (!appId) errs.application_id = 'Choose the vacancy this is about.';
        if (len < MIN || len > MAX) errs.content = `Write between ${MIN} and ${MAX} characters.`;
        setErrors(errs);
        if (Object.keys(errs).length) return;

        setBusy(true);
        try {
            await testimonials.create({ application_id: appId, content: content.trim(), show_name: showName });
            setNotice('Thank you! Your testimonial will appear after review.');
            setContent('');
            setAppId('');
            await load();
        } catch (err) {
            if (err instanceof ApiError && Object.keys(err.fields).length) setErrors(err.fields);
            setError(errText(err, 'Could not send the testimonial.'));
        } finally {
            setBusy(false);
        }
    }

    async function remove(id: string) {
        setError('');
        setNotice('');
        setDeletingId(id);
        try {
            await testimonials.remove(id);
            setNotice('Testimonial deleted.');
            setConfirmId(null);
            await load();
        } catch (err) {
            setError(errText(err, 'Could not delete the testimonial.'));
        } finally {
            setDeletingId(null);
        }
    }

    if (loading) return <PageSkeleton />;

    if (!user) {
        return (
            <SignInNotice title="Testimonials">
                Please{' '}
                <Link className="font-medium text-zinc-900 underline underline-offset-4" href="/login">
                    sign in
                </Link>{' '}
                to write a testimonial.
            </SignInNotice>
        );
    }

    if (!allowed) {
        return <SignInNotice title="Testimonials">Only active applicant accounts can write testimonials.</SignInNotice>;
    }

    const len = content.trim().length;

    return (
        <div className="py-4">
            <PageHeader
                eyebrow="Account"
                title="Your testimonials"
                subtitle="Got a job or internship through TCancy? Tell other students how it went. You can write one for each accepted application."
            />

            <div className="mt-10 grid items-start gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
                {/* Write */}
                <form
                    onSubmit={send}
                    noValidate
                    className={`rise flex flex-col gap-6 ${CARD} lg:sticky lg:top-24`}
                    style={stagger(1)}
                    aria-label="Write a testimonial"
                >
                    <h2 className={SECTION_LABEL}>Write a testimonial</h2>

                    {!loaded ? (
                        <div aria-hidden className="h-40 animate-pulse rounded-2xl bg-zinc-200/60" />
                    ) : eligible.length === 0 ? (
                        <p className="rounded-2xl border border-dashed border-zinc-300 px-5 py-6 leading-relaxed text-zinc-600">
                            {accepted.length === 0
                                ? 'You can write a testimonial once one of your applications is accepted.'
                                : 'You already wrote a testimonial for each of your accepted applications.'}{' '}
                            <Link href="/applications" className="font-medium text-zinc-900 underline underline-offset-4">
                                My applications
                            </Link>
                        </p>
                    ) : (
                        <>
                            <fieldset className="flex flex-col gap-2 text-sm" data-invalid={errors.application_id ? 'true' : undefined}>
                                <legend className="mb-2 font-medium text-zinc-900">Vacancy</legend>
                                {eligible.map((a) => {
                                    const on = appId === a.id;
                                    return (
                                        <label
                                            key={a.id}
                                            className={`flex cursor-pointer items-center gap-3 rounded-2xl border px-4 py-3 transition duration-300 ${EASE} focus-within:ring-4 focus-within:ring-zinc-900/10 ${on ? 'border-zinc-900 bg-zinc-50' : 'border-zinc-200 bg-white hover:border-zinc-400'
                                                }`}
                                        >
                                            <input type="radio" name="application" className="sr-only" checked={on} onChange={() => setAppId(a.id)} />
                                            <span className="min-w-0 flex-1">
                                                <span className="block font-medium text-zinc-900">{a.job.title}</span>
                                                <span className="block text-xs text-zinc-500">{a.job.company}</span>
                                            </span>
                                            <span
                                                aria-hidden
                                                className={`h-4 w-4 shrink-0 rounded-full border ${on ? 'border-[5px] border-zinc-900 bg-white' : 'border-zinc-300'}`}
                                            />
                                        </label>
                                    );
                                })}
                                {errors.application_id && (
                                    <p role="alert" className="text-[13px] text-red-700">
                                        {errors.application_id}
                                    </p>
                                )}
                            </fieldset>

                            <div className="flex flex-col gap-2 text-sm" data-invalid={errors.content ? 'true' : undefined}>
                                <label htmlFor="t-content" className="font-medium text-zinc-900">
                                    Your story
                                </label>
                                <textarea
                                    id="t-content"
                                    className={textareaClass}
                                    rows={6}
                                    value={content}
                                    onChange={(e) => {
                                        setContent(e.target.value);
                                        setErrors((x) => ({ ...x, content: '' }));
                                    }}
                                    placeholder="What was the process like, and what would you tell the next student?"
                                />
                                <div className="flex items-start justify-between gap-3">
                                    <p role={errors.content ? 'alert' : undefined} className="text-[13px] text-red-700">
                                        {errors.content}
                                    </p>
                                    <span className={`shrink-0 font-mono text-xs ${len > MAX ? 'text-red-700' : 'text-zinc-400'}`}>
                                        {len}/{MAX}
                                    </span>
                                </div>
                            </div>

                            <label className="flex cursor-pointer items-start gap-3 text-sm text-zinc-700">
                                <input type="checkbox" className="peer sr-only" checked={showName} onChange={(e) => setShowName(e.target.checked)} />
                                <span
                                    aria-hidden
                                    className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-md border transition peer-focus-visible:ring-4 peer-focus-visible:ring-zinc-900/10 ${showName ? 'border-zinc-900 bg-zinc-900 text-zinc-50' : 'border-zinc-300 bg-white'
                                        }`}
                                >
                                    {showName && <Check size={12} weight="bold" />}
                                </span>
                                <span className="leading-relaxed">
                                    Show my first name and company
                                    <span className="block text-xs text-zinc-500">Leave it off to stay anonymous.</span>
                                </span>
                            </label>

                            <button type="submit" disabled={busy} className={BTN_PRIMARY}>
                                {busy ? 'Sending...' : 'Send testimonial'}
                            </button>
                        </>
                    )}

                    {notice && (
                        <p role="status" className="text-sm font-medium text-zinc-900">
                            {notice}
                        </p>
                    )}
                    {error && <FormAlert>{error}</FormAlert>}
                </form>

                {/* List */}
                <section className={`rise ${CARD}`} style={stagger(2)} aria-label="Your testimonials">
                    <div className="flex items-baseline justify-between gap-4">
                        <h2 className={SECTION_LABEL}>Written by you</h2>
                        {loaded && <span className="font-mono text-xs text-zinc-500">{mine.length}</span>}
                    </div>

                    {!loaded ? (
                        <div aria-hidden className="mt-6 h-32 animate-pulse rounded-2xl bg-zinc-200/60" />
                    ) : loadError ? (
                        <div className="mt-6 flex flex-col items-start gap-3">
                            <FormAlert>{loadError}</FormAlert>
                            <button type="button" onClick={load} className={BTN_OUTLINE}>
                                Try again
                            </button>
                        </div>
                    ) : mine.length === 0 ? (
                        <p className="mt-6 rounded-2xl border border-dashed border-zinc-300 px-6 py-8 text-zinc-500">
                            Nothing here yet. Your testimonials will show up here with their review status.
                        </p>
                    ) : (
                        <ul className="mt-6 divide-y divide-zinc-200 border-y border-zinc-200">
                            {mine.map((t) => {
                                const s = STATUS[t.status] ?? STATUS.pending;
                                const job = jobOf(t.application_id);
                                return (
                                    <li key={t.id} className="flex flex-col gap-4 py-6">
                                        <div className="flex flex-wrap items-center justify-between gap-3">
                                            <div className="min-w-0">
                                                {job ? (
                                                    <Link
                                                        href={`/applications/${t.application_id}`}
                                                        className="font-semibold tracking-tight text-zinc-900 underline-offset-4 hover:underline"
                                                    >
                                                        {job.title}
                                                    </Link>
                                                ) : (
                                                    <span className="font-semibold tracking-tight text-zinc-900">Testimonial</span>
                                                )}
                                                <p className="mt-0.5 text-sm text-zinc-500">
                                                    {job ? `${job.company} · ` : ''}
                                                    {formatDate(t.created_at)}
                                                </p>
                                            </div>
                                            <Pill tone={s.tone}>{s.label}</Pill>
                                        </div>

                                        <p className="whitespace-pre-wrap leading-relaxed text-zinc-700">{t.content}</p>

                                        <div className="flex flex-wrap items-center justify-between gap-3">
                                            <p className="text-xs text-zinc-500">
                                                {t.show_name ? 'Name shown' : 'Anonymous'} · {s.hint}
                                            </p>
                                            {confirmId === t.id ? (
                                                <div className="flex items-center gap-2">
                                                    <button type="button" disabled={deletingId === t.id} onClick={() => remove(t.id)} className={BTN_DANGER}>
                                                        {deletingId === t.id ? 'Deleting...' : 'Yes, delete'}
                                                    </button>
                                                    <button type="button" onClick={() => setConfirmId(null)} className={BTN_OUTLINE}>
                                                        Cancel
                                                    </button>
                                                </div>
                                            ) : (
                                                <button
                                                    type="button"
                                                    onClick={() => setConfirmId(t.id)}
                                                    className="inline-flex min-h-9 items-center gap-1.5 rounded-full px-3 text-sm text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-900"
                                                >
                                                    <Trash size={16} />
                                                    Delete
                                                </button>
                                            )}
                                        </div>
                                    </li>
                                );
                            })}
                        </ul>
                    )}
                </section>
            </div>
        </div>
    );
}