'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import FormField, { inputClass } from '@/components/FormField';
import type { Job } from '@/components/JobCard';
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
    if (!window.confirm('Withdraw this application?')) return;
    setError('');
    setNotice('');
    setBusy(true);
    try {
      await api(`/me/applications/${id}`, { method: 'DELETE' });
      setNotice('Application withdrawn.');
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
    if (!window.confirm('Delete this testimonial?')) return;
    setError('');
    setNotice('');
    setBusy(true);
    try {
      await api(`/testimonials/${tid}`, { method: 'DELETE' });
      setNotice('Testimonial deleted.');
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not delete the testimonial.');
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <p className="text-sm text-gray-600">Loading...</p>;
  if (!allowed) return <p className="text-sm">Only active applicants can see applications.</p>;

  const final = app && (app.status === 'rejected' || app.status === 'withdrawn');

  return (
    <div>
      <Link href="/applications" className="text-sm underline">
        Back to my applications
      </Link>
      {error && <p className="mt-3 text-sm text-red-700">{error}</p>}
      {notice && <p className="mt-3 text-sm text-green-700">{notice}</p>}
      {!app && !error && <p className="mt-3 text-sm text-gray-600">Loading...</p>}
      {app && (
        <div className="mt-3 space-y-4 text-sm">
          <div>
            <h1 className="text-2xl font-semibold">{app.job.title}</h1>
            <p className="text-gray-700">
              {app.job.company} ·{' '}
              <Link href={`/vacancy/${app.job.id}`} className="underline">
                View vacancy
              </Link>
            </p>
            <p className="text-gray-500">
              Status: {app.status} · Applied {app.created_at.slice(0, 10)}
            </p>
          </div>
          <div>
            <h2 className="font-semibold">Cover note</h2>
            <p className="whitespace-pre-wrap">{app.cover_note || 'None.'}</p>
          </div>
          <p className="text-gray-700">
            CV: {app.cv_document_id ? 'attached' : 'removed'} · Intro video:{' '}
            {app.intro_video_document_id ? 'attached' : 'none'}
          </p>
          <div>
            <h2 className="font-semibold">History</h2>
            <ul className="divide-y rounded border">
              {app.history.map((h, i) => (
                <li key={i} className="p-2">
                  {h.from_status ? `${h.from_status} → ${h.to_status}` : h.to_status} ·{' '}
                  {h.created_at.slice(0, 10)}
                  {h.note && <span className="text-gray-600"> · {h.note}</span>}
                </li>
              ))}
            </ul>
          </div>
          {!final && (
            <button className="rounded border px-3 py-1" disabled={busy} onClick={withdraw}>
              Withdraw application
            </button>
          )}
          {app.status === 'accepted' && (
            <div className="border-t pt-4">
              <h2 className="font-semibold">Testimonial</h2>
              {testimonial ? (
                <div className="mt-2">
                  <p className="whitespace-pre-wrap">{testimonial.content}</p>
                  <p className="text-gray-500">
                    Status: {testimonial.status} · {testimonial.show_name ? 'Name shown' : 'Anonymous'}
                  </p>
                  <button
                    className="mt-2 rounded border px-3 py-1"
                    disabled={busy}
                    onClick={() => removeTestimonial(testimonial.id)}
                  >
                    Delete testimonial
                  </button>
                </div>
              ) : (
                <form onSubmit={sendTestimonial} className="mt-2 max-w-lg space-y-3">
                  <FormField label="Your experience (20 to 1000 characters)" error={contentError}>
                    <textarea
                      className={inputClass}
                      rows={4}
                      value={content}
                      onChange={(e) => setContent(e.target.value)}
                    />
                  </FormField>
                  <label className="flex items-center gap-2">
                    <input type="checkbox" checked={showName} onChange={(e) => setShowName(e.target.checked)} />
                    Show my first name and company
                  </label>
                  <button type="submit" disabled={busy} className="rounded border px-3 py-1">
                    Send testimonial
                  </button>
                </form>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
