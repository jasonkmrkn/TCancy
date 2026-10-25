'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import FormField, { inputClass } from '@/components/FormField';
import { api, ApiError, buildUrl } from '@/lib/api';
import { useAuth } from '@/lib/auth';

type Doc = { id: string; type: 'cv' | 'ktp' | 'intro_video'; ext: string; size: number; created_at: string };

const TYPES: { value: Doc['type']; label: string; exts: string[]; hint: string }[] = [
  { value: 'cv', label: 'CV', exts: ['pdf'], hint: 'PDF, up to 5 MB, max 5 files.' },
  {
    value: 'ktp',
    label: 'ID card (KTP)',
    exts: ['jpg', 'jpeg', 'png', 'pdf'],
    hint: 'JPG, PNG or PDF, up to 5 MB. A new upload replaces the old one.',
  },
  { value: 'intro_video', label: 'Intro video', exts: ['mp4'], hint: 'MP4, up to 50 MB, max 5 files.' },
];

function formatSize(n: number): string {
  if (n >= 1024 * 1024) return (n / (1024 * 1024)).toFixed(1) + ' MB';
  if (n >= 1024) return Math.round(n / 1024) + ' KB';
  return n + ' B';
}

export default function DocumentsPage() {
  const { user, loading } = useAuth();
  const [docs, setDocs] = useState<Doc[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [type, setType] = useState<Doc['type']>('cv');
  const [file, setFile] = useState<File | null>(null);
  const [fileKey, setFileKey] = useState(0);
  const [fileError, setFileError] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);

  const allowed = user?.role === 'applicant' && user.status === 'active';

  const load = useCallback(async () => {
    try {
      setDocs(await api<Doc[]>('/me/documents'));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load documents.');
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    if (allowed) load();
  }, [allowed, load]);

  async function upload(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setNotice('');
    setFileError('');
    if (!file) {
      setFileError('Choose a file first.');
      return;
    }
    const info = TYPES.find((t) => t.value === type)!;
    const ext = file.name.includes('.') ? file.name.split('.').pop()!.toLowerCase() : '';
    if (!info.exts.includes(ext)) {
      setFileError('Allowed file types: ' + info.exts.join(', ') + '.');
      return;
    }
    const form = new FormData();
    form.append('type', type);
    form.append('file', file);
    setBusy(true);
    try {
      await api('/me/documents', { method: 'POST', body: form });
      setNotice('File uploaded.');
      setFile(null);
      setFileKey((k) => k + 1);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong.');
    } finally {
      setBusy(false);
    }
  }

  async function remove(doc: Doc) {
    if (!window.confirm('Delete this file?')) return;
    setError('');
    setNotice('');
    try {
      await api(`/me/documents/${doc.id}`, { method: 'DELETE' });
      setNotice('File deleted.');
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong.');
    }
  }

  if (loading) return <p className="text-sm text-gray-600">Checking session...</p>;

  if (!user) {
    return (
      <div className="text-sm">
        <h1 className="text-2xl font-bold">Documents</h1>
        <p className="mt-4">
          Please{' '}
          <Link className="underline" href="/login">
            sign in
          </Link>{' '}
          to manage your documents.
        </p>
      </div>
    );
  }

  if (!allowed) {
    return (
      <div className="text-sm">
        <h1 className="text-2xl font-bold">Documents</h1>
        <p className="mt-4">Only active applicant accounts can upload documents.</p>
      </div>
    );
  }

  const current = TYPES.find((t) => t.value === type)!;

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold">Documents</h1>

      <form onSubmit={upload} className="mt-4 flex flex-col gap-3" noValidate>
        <FormField label="Type">
          <select
            className={inputClass}
            value={type}
            onChange={(e) => {
              setType(e.target.value as Doc['type']);
              setFile(null);
              setFileKey((k) => k + 1);
              setFileError('');
            }}
          >
            {TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </FormField>
        <FormField label="File" error={fileError}>
          <input
            key={fileKey}
            className={inputClass}
            type="file"
            accept={current.exts.map((x) => '.' + x).join(',')}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </FormField>
        <p className="text-sm text-gray-600">{current.hint}</p>
        {error && <p className="text-sm text-red-700">{error}</p>}
        {notice && <p className="text-sm text-green-700">{notice}</p>}
        <button className="self-start rounded border px-3 py-1 text-sm" type="submit" disabled={busy}>
          {busy ? 'Uploading...' : 'Upload'}
        </button>
      </form>

      {TYPES.map((t) => {
        const list = docs.filter((d) => d.type === t.value);
        return (
          <section key={t.value} className="mt-8">
            <h2 className="text-lg font-semibold">{t.label}</h2>
            {!loaded ? (
              <p className="mt-2 text-sm text-gray-600">Loading...</p>
            ) : list.length === 0 ? (
              <p className="mt-2 text-sm text-gray-600">No files uploaded.</p>
            ) : (
              <table className="mt-2 w-full text-left text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="py-1 pr-2">Format</th>
                    <th className="py-1 pr-2">Size</th>
                    <th className="py-1 pr-2">Uploaded</th>
                    <th className="py-1" />
                  </tr>
                </thead>
                <tbody>
                  {list.map((d) => (
                    <tr key={d.id} className="border-b">
                      <td className="py-1 pr-2">{d.ext.replace(/^\./, '').toUpperCase()}</td>
                      <td className="py-1 pr-2">{formatSize(d.size)}</td>
                      <td className="py-1 pr-2">{new Date(d.created_at).toLocaleString()}</td>
                      <td className="flex gap-3 py-1">
                        <a className="underline" href={buildUrl(`/me/documents/${d.id}/download`)}>
                          Download
                        </a>
                        <button className="text-red-700 underline" type="button" onClick={() => remove(d)}>
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        );
      })}
    </div>
  );
}
