'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import { ArrowLeft, ArrowUpRight, Check, CheckCircle, FilePdf, FileVideo } from '@phosphor-icons/react';
import { stagger } from '@/components/AuthShell';
import { FormAlert, textareaClass } from '@/components/FormField';
import { SECTION_LABEL } from '@/components/home/Band';
import type { Job } from '@/components/JobCard';
import { BTN_DANGER, BTN_DANGER_OUTLINE, BTN_OUTLINE, BTN_PRIMARY, CARD, EASE, Pill, SignInNotice } from '@/components/ui';
import { api, ApiError } from '@/lib/api';
import { useAuth } from '@/lib/auth';

type Detail = {
  id: string;
  job: Job;
  status: string;
  cover_note: string | null;
  cv_document_id: string | null;
  intro_video_document_id: string | null;
  created_at: string;
  history: { from_status: string | null; to_status: string; note: string | null; created_at: string }[];
};

type Testimonial = {
  id: string;
  application_id: string;
  content: string;
  show_name: boolean;
  status: string;
  created_at: string;
};

const STATUS_LABEL: Record<string, string> = {
  submitted: 'Submitted',
  shortlisted: 'Shortlisted',
  accepted: 'Accepted',
  rejected: 'Rejected',
  withdrawn: 'Withdrawn',
};

const STATUS_MESSAGE: Record<string, string> = {
  submitted: 'Your application is with the vacancy owner. You will see the status change here.',
  shortlisted: 'You made the shortlist. The vacancy owner may reach out to you.',
  accepted: 'Congratulations, you were accepted. Consider sharing your experience below.',
  rejected: 'The vacancy owner did not move forward with this application.',
  withdrawn: 'You withdrew this application.',
};

function statusTone(status: string): 'solid' | 'outline' | 'muted' {
  return status === 'accepted' ? 'solid' : status === 'rejected' || status === 'withdrawn' ? 'muted' : 'outline';
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

function PageSkeleton() {
  return (
    <div aria-hidden className="animate-pulse py-4">
      <div className="h-4 w-40 rounded-full bg-zinc-200/70" />
      <div className="mt-8 h-12 w-96 max-w-full rounded-full bg-zinc-200/70" />
      <div className="mt-10 grid gap-6 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <div className="h-80 rounded-[2.5rem] bg-zinc-200/60" />
        <div className="h-80 rounded-[2.5rem] bg-zinc-200/60" />
      </div>
    </div>
  );
}

function FileRow({ icon: Icon, label, present, missing }: { icon: React.ElementType; label: string; present: boolean; missing: string }) {
  return (
    <li className="flex items-center gap-4 py-4">
      <span aria-hidden className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-zinc-100 text-zinc-700">
        <Icon size={20} />
      </span>
      <span className="flex-1 font-medium text-zinc-900">{label}</span>
      <Pill tone={present ? 'solid' : 'outline'}>{present ? 'Attached' : missing}</Pill>
    </li>
  );
}

export default function ApplicationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user, loading } = useAuth();
  const [app, setApp] = useState<Detail | null>(null);
  const [testimonial, setTestimonial] = useState<Testimonial | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [content, setContent] = useState('');
  const [showName, setShowName] = useState(false);
  const [contentError, setContentError] = useState('');
  const [confirmWithdraw, setConfirmWithdraw] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const allowed = user?.role === 'applicant' && user.status === 'active';

  const load = useCallback(async () => {
    try {
      const a = await api<Detail>(`/me/applications/${id}`);
      setApp(a);
      if (a.status === 'accepted') {
        const t = await api<{ items: Testimonial[] }>('/me/testimonials');
        setTestimonial(t.items.find((x) => x.application_id === a.id) ?? null);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load the application.');
    }
  }, [id]);

  useEffect(() => {
    if (allowed) load();
  }, [allowed, load]);

  async function withdraw() {
    setError('');
    setNotice('');
    setBusy(true);
    try {
      await api(`/me/applications/${id}`, { method: 'DELETE' });
      setNotice('Application withdrawn.');
      setConfirmWithdraw(false);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not withdraw the application.');
    } finally {
      setBusy(false);
    }
  }

  async function sendTestimonial(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setNotice('');
    setContentError('');
    const text = content.trim();
    if (text.length < 20 || text.length > 1000) {
      setContentError('The testimonial must have 20 to 1000 characters.');
      return;
    }
    setBusy(true);
    try {
      await api('/testimonials', {
        method: 'POST',
        body: { application_id: id, content: text, show_name: showName },
      });
      setNotice('Thank you! Your testimonial will appear after review.');
      setContent('');
      await load();
    } catch (err) {
      if (err instanceof ApiError && err.fields['content']) setContentError(err.fields['content']);
      else setError(err instanceof ApiError ? err.message : 'Could not send the testimonial.');
    } finally {
      setBusy(false);
    }
  }

  async function removeTestimonial(tid: string) {
    setError('');
    setNotice('');
    setBusy(true);
    try {
      await api(`/testimonials/${tid}`, { method: 'DELETE' });
      setNotice('Testimonial deleted.');
      setConfirmDelete(false);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not delete the testimonial.');
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <PageSkeleton />;
  if (!allowed) {
    return (
      <SignInNotice title="Application">
        Only active applicants can see applications.{' '}
        {!user && (
          <Link href="/login" className="font-medium text-zinc-900 underline underline-offset-4">
            Sign in
          </Link>
        )}
      </SignInNotice>
    );
  }

  const final = !!app && (app.status === 'rejected' || app.status === 'withdrawn');
  const back = (
    <Link
      href="/applications"
      className="inline-flex items-center gap-1.5 text-sm font-medium text-zinc-600 transition-colors hover:text-zinc-900"
    >
      <ArrowLeft size={14} weight="bold" />
      My applications
    </Link>
  );

  if (!app && error) {
    return (
      <div className="py-4">
        {back}
        <div className="mt-8 flex flex-col items-start gap-4">
          <FormAlert>{error}</FormAlert>
          <Link href="/applications" className={BTN_OUTLINE}>
            Back to my applications
          </Link>
        </div>
      </div>
    );
  }
  if (!app) return <PageSkeleton />;

  const history = [...app.history].reverse(); // newest first

  return (
    <div className="py-4">
      {back}

      <header className="rise mt-8 flex flex-wrap items-end justify-between gap-6" style={stagger(0)}>
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <p className={SECTION_LABEL}>{app.job.company}</p>
            <Pill tone={statusTone(app.status)}>{STATUS_LABEL[app.status] ?? app.status}</Pill>
          </div>
          <h1 className="mt-3 max-w-[22ch] text-4xl font-semibold leading-[1.05] tracking-tighter text-zinc-900 md:text-5xl">
            {app.job.title}
          </h1>
          <p className="mt-4 font-mono text-sm text-zinc-500">Applied {formatDate(app.created_at)}</p>
        </div>
        <Link href={`/vacancy/${app.job.id}`} className={BTN_OUTLINE}>
          View vacancy
          <ArrowUpRight size={16} />
        </Link>
      </header>

      <div role="status" aria-live="polite" className="mt-6 empty:hidden">
        {notice && (
          <p className="inline-flex items-center gap-2 rounded-full bg-zinc-100 px-4 py-2 text-sm text-zinc-800">
            <CheckCircle size={18} weight="fill" className="text-zinc-900" />
            {notice}
          </p>
        )}
      </div>
      {error && (
        <div className="mt-4">
          <FormAlert>{error}</FormAlert>
        </div>
      )}

      <div className="mt-10 grid items-start gap-6 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        {/* Left: status + notes */}
        <div className="flex flex-col gap-6">
          <section className={`rise ${CARD}`} style={stagger(1)} aria-label="Status history">
            <h2 className={SECTION_LABEL}>Where it stands</h2>
            <p className="mt-4 max-w-[52ch] leading-relaxed text-zinc-600">{STATUS_MESSAGE[app.status]}</p>

            <ol className="mt-8">
              {history.map((h, i) => (
                <li key={i} className="relative flex gap-5 pb-8 last:pb-0">
                  {i < history.length - 1 && (
                    <span aria-hidden className="absolute left-[0.6875rem] top-6 h-[calc(100%-1.5rem)] w-px bg-zinc-200" />
                  )}
                  <span
                    aria-hidden
                    className={`relative mt-1 grid h-6 w-6 shrink-0 place-items-center rounded-full ${i === 0 ? 'bg-zinc-900 text-zinc-50' : 'border border-zinc-300 bg-white text-zinc-400'
                      }`}
                  >
                    {i === 0 ? <Check size={12} weight="bold" /> : <span className="h-1.5 w-1.5 rounded-full bg-zinc-300" />}
                  </span>
                  <div className="min-w-0">
                    <p className="font-medium text-zinc-900">
                      {STATUS_LABEL[h.to_status] ?? h.to_status}
                      {h.from_status && (
                        <span className="ml-2 text-sm font-normal text-zinc-500">
                          from {(STATUS_LABEL[h.from_status] ?? h.from_status).toLowerCase()}
                        </span>
                      )}
                    </p>
                    <p className="mt-0.5 font-mono text-xs text-zinc-500">{formatDate(h.created_at)}</p>
                    {h.note && <p className="mt-2 rounded-2xl bg-zinc-50 px-4 py-3 text-sm text-zinc-600">{h.note}</p>}
                  </div>
                </li>
              ))}
            </ol>
          </section>

          <section className={`rise ${CARD}`} style={stagger(2)} aria-label="Cover note">
            <h2 className={SECTION_LABEL}>Your cover note</h2>
            {app.cover_note ? (
              <p className="mt-5 max-w-[64ch] whitespace-pre-wrap leading-relaxed text-zinc-700">{app.cover_note}</p>
            ) : (
              <p className="mt-5 text-zinc-500">You did not add a cover note.</p>
            )}
          </section>
        </div>

        {/* Right: files + actions + testimonial */}
        <aside className="flex flex-col gap-6 lg:sticky lg:top-24">
          <section
            className="rise rounded-[2.5rem] border border-zinc-200/60 bg-white px-8 py-6 shadow-[0_20px_40px_-15px_rgba(24,24,27,0.08)]"
            style={stagger(2)}
            aria-label="Submitted files"
          >
            <h2 className={SECTION_LABEL}>What you sent</h2>
            <ul className="mt-2 divide-y divide-zinc-200">
              <FileRow icon={FilePdf} label="CV" present={!!app.cv_document_id} missing="Removed" />
              <FileRow icon={FileVideo} label="Intro video" present={!!app.intro_video_document_id} missing="None" />
            </ul>
          </section>

          {!final && (
            <section className="rise rounded-[2.5rem] border border-zinc-200/60 bg-white p-8" style={stagger(3)} aria-label="Withdraw">
              <h2 className="text-lg font-semibold tracking-tight text-zinc-900">Changed your mind?</h2>
              <p className="mt-2 text-sm leading-relaxed text-zinc-500">
                Withdrawing tells the vacancy owner you are no longer interested. It cannot be undone.
              </p>
              {confirmWithdraw ? (
                <div className="mt-5 flex flex-wrap gap-3">
                  <button type="button" className={BTN_DANGER} disabled={busy} onClick={withdraw}>
                    {busy ? 'Withdrawing...' : 'Yes, withdraw'}
                  </button>
                  <button type="button" className={BTN_OUTLINE} onClick={() => setConfirmWithdraw(false)}>
                    Keep it
                  </button>
                </div>
              ) : (
                <button type="button" className={`${BTN_DANGER_OUTLINE} mt-5`} onClick={() => setConfirmWithdraw(true)}>
                  Withdraw application
                </button>
              )}
            </section>
          )}

          {app.status === 'accepted' && (
            <section
              className="rise relative overflow-hidden rounded-[2.5rem] border border-white/10 bg-zinc-950 p-8 text-zinc-50 shadow-[inset_0_1px_0_rgba(255,255,255,0.1)]"
              style={stagger(4)}
              aria-label="Testimonial"
            >
              <div
                aria-hidden
                className="absolute inset-x-0 top-0 h-40 bg-[radial-gradient(ellipse_at_top_left,rgba(255,255,255,0.08),transparent_70%)]"
              />
              <h2 className="relative text-xs font-semibold uppercase tracking-[0.14em] text-zinc-400">Testimonial</h2>

              {testimonial ? (
                <div className="relative mt-5">
                  <p className="whitespace-pre-wrap leading-relaxed text-zinc-100">{testimonial.content}</p>
                  <p className="mt-4 flex flex-wrap items-center gap-2 font-mono text-xs text-zinc-400">
                    <span className="rounded-full border border-white/20 px-2.5 py-0.5 uppercase tracking-wider">{testimonial.status}</span>
                    {testimonial.show_name ? 'Name shown' : 'Anonymous'}
                  </p>
                  {confirmDelete ? (
                    <div className="mt-6 flex flex-wrap gap-3">
                      <button type="button" disabled={busy} onClick={() => removeTestimonial(testimonial.id)} className={`${BTN_DANGER}`}>
                        {busy ? 'Deleting...' : 'Yes, delete'}
                      </button>
                      <button
                        type="button"
                        onClick={() => setConfirmDelete(false)}
                        className="inline-flex min-h-11 items-center rounded-full border border-white/20 px-5 text-sm font-medium text-zinc-50 transition hover:border-white/50"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setConfirmDelete(true)}
                      className="mt-6 inline-flex min-h-11 items-center rounded-full border border-white/20 px-5 text-sm font-medium text-zinc-50 transition hover:border-white/50"
                    >
                      Delete testimonial
                    </button>
                  )}
                </div>
              ) : (
                <form onSubmit={sendTestimonial} noValidate className="relative mt-5 flex flex-col gap-4">
                  <p className="text-sm leading-relaxed text-zinc-400">
                    Tell other students how it went. It appears on the home page after an admin reviews it.
                  </p>
                  <div className="flex flex-col gap-2 text-zinc-900">
                    <textarea
                      className={textareaClass}
                      rows={5}
                      value={content}
                      onChange={(e) => setContent(e.target.value)}
                      aria-label="Your experience"
                      placeholder="Your experience (20 to 1000 characters)"
                    />
                    {contentError && (
                      <p role="alert" className="text-[13px] text-red-400">
                        {contentError}
                      </p>
                    )}
                  </div>
                  <div className="-mt-2 flex justify-end">
                    <span className={`font-mono text-xs ${content.trim().length > 1000 ? 'text-red-400' : 'text-zinc-500'}`}>
                      {content.trim().length}/1000
                    </span>
                  </div>
                  <label className="flex cursor-pointer items-start gap-3 text-sm text-zinc-300">
                    <input type="checkbox" className="peer sr-only" checked={showName} onChange={(e) => setShowName(e.target.checked)} />
                    <span
                      aria-hidden
                      className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-md border transition peer-focus-visible:ring-4 peer-focus-visible:ring-white/20 ${showName ? 'border-zinc-50 bg-zinc-50 text-zinc-900' : 'border-white/30'
                        }`}
                    >
                      {showName && <Check size={12} weight="bold" />}
                    </span>
                    Show my first name and company
                  </label>
                  <button
                    type="submit"
                    disabled={busy}
                    className={`inline-flex min-h-11 items-center justify-center rounded-full bg-zinc-50 px-5 text-sm font-medium text-zinc-900 transition duration-300 ${EASE} hover:bg-white active:scale-[0.98] disabled:opacity-50`}
                  >
                    {busy ? 'Sending...' : 'Send testimonial'}
                  </button>
                </form>
              )}
            </section>
          )}

          {final && (
            <Link href="/vacancy" className={`${BTN_PRIMARY} self-start`}>
              Browse more vacancies
            </Link>
          )}
        </aside>
      </div>
    </div>
  );
}