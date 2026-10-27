'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  CheckCircle,
  DownloadSimple,
  FileImage,
  FilePdf,
  FileVideo,
  Trash,
  UploadSimple,
} from '@phosphor-icons/react';
import { stagger } from '@/components/AuthShell';
import Chip from '@/components/Chip';
import { FormAlert } from '@/components/FormField';
import { SECTION_LABEL } from '@/components/home/Band';
import { BTN_OUTLINE, BTN_PRIMARY, CARD, EASE, PageHeader, PageSkeleton, Pill, SignInNotice } from '@/components/ui';
import { api, ApiError, buildUrl } from '@/lib/api';
import { useAuth } from '@/lib/auth';

type Doc = { id: string; type: 'cv' | 'ktp' | 'intro_video'; ext: string; size: number; created_at: string };

const TYPES: { value: Doc['type']; label: string; exts: string[]; hint: string; required?: boolean }[] = [
  { value: 'cv', label: 'CV', exts: ['pdf'], hint: 'PDF, up to 5 MB, max 5 files.', required: true },
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

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

function FileIcon({ ext }: { ext: string }) {
  const e = ext.replace(/^\./, '').toLowerCase();
  const Icon = e === 'mp4' ? FileVideo : e === 'pdf' ? FilePdf : FileImage;
  return (
    <span aria-hidden className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-zinc-100 text-zinc-700">
      <Icon size={22} weight="regular" />
    </span>
  );
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
  const [dragging, setDragging] = useState(false);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

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

  function pick(f: File | null) {
    setNotice('');
    setFileError('');
    setFile(f);
  }

  function changeType(t: Doc['type']) {
    setType(t);
    setFile(null);
    setFileKey((k) => k + 1);
    setFileError('');
    setNotice('');
  }

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
    setError('');
    setNotice('');
    setDeletingId(doc.id);
    try {
      await api(`/me/documents/${doc.id}`, { method: 'DELETE' });
      setNotice('File deleted.');
      setConfirmId(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong.');
    } finally {
      setDeletingId(null);
    }
  }

  if (loading) return <PageSkeleton />;

  if (!user) {
    return (
      <SignInNotice title="Documents">
        Please{' '}
        <Link className="font-medium text-zinc-900 underline underline-offset-4" href="/login">
          sign in
        </Link>{' '}
        to manage your documents.
      </SignInNotice>
    );
  }

  if (!allowed) {
    return <SignInNotice title="Documents">Only active applicant accounts can upload documents.</SignInNotice>;
  }

  const current = TYPES.find((t) => t.value === type)!;

  return (
    <div className="py-4">
      <PageHeader
        eyebrow="Account"
        title="Your documents"
        subtitle="Upload the files vacancy owners ask for. You choose which CV and video to attach each time you apply."
      />

      <div className="mt-10 grid items-start gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        {/* Upload */}
        <form
          onSubmit={upload}
          noValidate
          className={`rise flex flex-col gap-6 ${CARD} lg:sticky lg:top-24`}
          style={stagger(1)}
          aria-label="Upload a file"
        >
          <h2 className={SECTION_LABEL}>Upload a file</h2>

          <fieldset className="flex flex-col gap-3 text-sm">
            <legend className="mb-2 font-medium text-zinc-900">Type</legend>
            <div role="group" className="flex flex-wrap gap-2">
              {TYPES.map((t) => (
                <Chip key={t.value} selected={type === t.value} onClick={() => changeType(t.value)}>
                  {t.label}
                </Chip>
              ))}
            </div>
          </fieldset>

          <div data-invalid={fileError ? 'true' : undefined} className="group flex flex-col gap-2">
            <label
              htmlFor="doc-file"
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                const f = e.dataTransfer.files?.[0];
                if (f) pick(f);
              }}
              className={`flex cursor-pointer flex-col items-center gap-3 rounded-[2rem] border border-dashed px-6 py-10 text-center transition duration-300 ${EASE} focus-within:border-zinc-900 focus-within:ring-4 focus-within:ring-zinc-900/10 group-data-[invalid=true]:border-red-400 ${dragging ? 'border-zinc-900 bg-zinc-100' : 'border-zinc-300 bg-zinc-50/60 hover:border-zinc-500 hover:bg-zinc-50'
                }`}
            >
              <span className="grid h-12 w-12 place-items-center rounded-full bg-white text-zinc-800 shadow-[0_8px_20px_-8px_rgba(24,24,27,0.2)]">
                <UploadSimple size={22} weight="regular" />
              </span>
              {file ? (
                <span className="min-w-0 max-w-full">
                  <span className="block truncate text-sm font-medium text-zinc-900">{file.name}</span>
                  <span className="mt-0.5 block font-mono text-xs text-zinc-500">{formatSize(file.size)}</span>
                </span>
              ) : (
                <span className="text-sm text-zinc-600">
                  <span className="font-medium text-zinc-900">Choose a file</span> or drop it here
                </span>
              )}
              <input
                id="doc-file"
                key={fileKey}
                ref={inputRef}
                className="sr-only"
                type="file"
                accept={current.exts.map((x) => '.' + x).join(',')}
                onChange={(e) => pick(e.target.files?.[0] ?? null)}
              />
            </label>
            {fileError ? (
              <p role="alert" className="text-[13px] text-red-700">
                {fileError}
              </p>
            ) : (
              <p className="text-[13px] text-zinc-500">{current.hint}</p>
            )}
          </div>

          {error && <FormAlert>{error}</FormAlert>}

          <div className="flex flex-wrap items-center gap-4">
            <button className={BTN_PRIMARY} type="submit" disabled={busy}>
              {busy ? 'Uploading...' : 'Upload'}
            </button>
            {file && !busy && (
              <button type="button" className={BTN_OUTLINE} onClick={() => changeType(type)}>
                Clear
              </button>
            )}
          </div>
          <p role="status" aria-live="polite" className="-mt-2 min-h-5 text-sm text-zinc-600">
            {notice && (
              <span className="inline-flex items-center gap-2">
                <CheckCircle size={18} weight="fill" className="text-zinc-900" />
                {notice}
              </span>
            )}
          </p>
        </form>

        {/* Lists */}
        <div className="flex flex-col gap-6">
          {TYPES.map((t, i) => {
            const list = docs.filter((d) => d.type === t.value);
            return (
              <section
                key={t.value}
                className="rise rounded-[2.5rem] border border-zinc-200/60 bg-white p-8 shadow-[0_20px_40px_-15px_rgba(24,24,27,0.08)]"
                style={stagger(i + 2)}
                aria-label={t.label}
              >
                <div className="flex items-center justify-between gap-4">
                  <h2 className="text-xl font-semibold tracking-tight text-zinc-900">{t.label}</h2>
                  {loaded &&
                    (list.length > 0 ? (
                      <Pill tone="solid">{list.length} uploaded</Pill>
                    ) : (
                      <Pill>{t.required ? 'Missing' : 'None'}</Pill>
                    ))}
                </div>

                {!loaded ? (
                  <div aria-hidden className="mt-6 flex animate-pulse flex-col gap-3">
                    <div className="h-16 rounded-2xl bg-zinc-200/60" />
                  </div>
                ) : list.length === 0 ? (
                  <p className="mt-4 text-sm leading-relaxed text-zinc-500">
                    No files uploaded.{' '}
                    <button
                      type="button"
                      onClick={() => changeType(t.value)}
                      className="font-medium text-zinc-900 underline underline-offset-4"
                    >
                      Upload {t.label}
                    </button>
                  </p>
                ) : (
                  <ul className="mt-6 divide-y divide-zinc-200 border-y border-zinc-200">
                    {list.map((d) => (
                      <li key={d.id} className="flex flex-wrap items-center gap-x-4 gap-y-3 py-4">
                        <FileIcon ext={d.ext} />
                        <div className="min-w-[9rem] flex-1">
                          <p className="text-sm font-medium text-zinc-900">
                            {d.ext.replace(/^\./, '').toUpperCase()} file
                          </p>
                          <p className="mt-0.5 font-mono text-xs text-zinc-500">
                            {formatSize(d.size)} · {formatDate(d.created_at)}
                          </p>
                        </div>

                        {confirmId === d.id ? (
                          <div className="flex items-center gap-2">
                            <span className="text-sm text-zinc-600">Delete?</span>
                            <button
                              type="button"
                              disabled={deletingId === d.id}
                              onClick={() => remove(d)}
                              className="min-h-9 rounded-full bg-red-700 px-4 text-sm font-medium text-white transition duration-300 hover:bg-red-800 active:scale-[0.98] disabled:opacity-50"
                            >
                              {deletingId === d.id ? 'Deleting...' : 'Yes, delete'}
                            </button>
                            <button
                              type="button"
                              onClick={() => setConfirmId(null)}
                              className="min-h-9 rounded-full border border-zinc-200 px-4 text-sm text-zinc-700 transition duration-300 hover:border-zinc-400"
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <div className="flex items-center gap-2">
                            <a
                              href={buildUrl(`/me/documents/${d.id}/download`)}
                              className="inline-flex min-h-9 items-center gap-1.5 rounded-full border border-zinc-200 px-4 text-sm text-zinc-900 transition duration-300 hover:border-zinc-400 active:scale-[0.98]"
                            >
                              <DownloadSimple size={16} />
                              Download
                            </a>
                            <button
                              type="button"
                              aria-label={`Delete ${t.label} file`}
                              onClick={() => setConfirmId(d.id)}
                              className="grid h-9 w-9 place-items-center rounded-full text-zinc-500 transition duration-300 hover:bg-red-50 hover:text-red-700 active:scale-[0.96]"
                            >
                              <Trash size={18} />
                            </button>
                          </div>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            );
          })}
        </div>
      </div>
    </div>
  );
}