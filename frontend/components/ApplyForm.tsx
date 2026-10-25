'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import FormField, { inputClass } from '@/components/FormField';
import { api, ApiError } from '@/lib/api';

type Doc = { id: string; type: 'cv' | 'ktp' | 'intro_video'; ext: string; size: number; created_at: string };

export default function ApplyForm({ jobId }: { jobId: string }) {
  const router = useRouter();
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const [cv, setCv] = useState('');
  const [video, setVideo] = useState('');
  const [note, setNote] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<Doc[]>('/me/documents')
      .then(setDocs)
      .catch((e) => {
        setDocs([]);
        setError(e instanceof ApiError ? e.message : 'Could not load your documents.');
      });
  }, []);

  const cvs = (docs ?? []).filter((d) => d.type === 'cv');
  const videos = (docs ?? []).filter((d) => d.type === 'intro_video');

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    const errs: Record<string, string> = {};
    if (!cv) errs.cv_document_id = 'Choose a CV.';
    if (note.length > 2000) errs.cover_note = 'The cover note can have at most 2000 characters.';
    setErrors(errs);
    if (Object.keys(errs).length) return;
    const body: Record<string, string> = { cv_document_id: cv };
    if (video) body.intro_video_document_id = video;
    if (note.trim()) body.cover_note = note.trim();
    setBusy(true);
    try {
      const res = await api<{ id: string }>(`/jobs/${jobId}/apply`, { method: 'POST', body });
      router.push(`/applications/${res.id}`);
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fields).length) {
        setErrors(err.fields);
        setError(err.message);
      } else {
        setError(err instanceof ApiError ? err.message : 'Could not submit the application.');
      }
      setBusy(false);
    }
  }

  if (!docs) return <p className="mt-4 text-sm text-gray-600">Loading...</p>;

  return (
    <form onSubmit={submit} className="mt-6 max-w-lg space-y-3 border-t pt-4">
      <h2 className="font-semibold">Apply for this vacancy</h2>
      {cvs.length === 0 && (
        <p className="text-sm text-gray-700">
          You need to upload a CV before applying. Go to{' '}
          <Link href="/documents" className="underline">
            Documents
          </Link>
          .
        </p>
      )}
      <FormField label="CV (required)" error={errors.cv_document_id}>
        <select className={inputClass} value={cv} onChange={(e) => setCv(e.target.value)}>
          <option value="">Select a CV</option>
          {cvs.map((d) => (
            <option key={d.id} value={d.id}>
              CV uploaded {d.created_at.slice(0, 10)} ({d.id.slice(0, 8)})
            </option>
          ))}
        </select>
      </FormField>
      <FormField label="Intro video (optional)" error={errors.intro_video_document_id}>
        <select className={inputClass} value={video} onChange={(e) => setVideo(e.target.value)}>
          <option value="">No video</option>
          {videos.map((d) => (
            <option key={d.id} value={d.id}>
              Video uploaded {d.created_at.slice(0, 10)} ({d.id.slice(0, 8)})
            </option>
          ))}
        </select>
      </FormField>
      <FormField label="Cover note (optional, up to 2000 characters)" error={errors.cover_note}>
        <textarea className={inputClass} rows={5} value={note} onChange={(e) => setNote(e.target.value)} />
      </FormField>
      {error && <p className="text-sm text-red-700">{error}</p>}
      <button type="submit" disabled={busy} className="rounded border px-3 py-1 text-sm">
        {busy ? 'Submitting...' : 'Submit application'}
      </button>
    </form>
  );
}
