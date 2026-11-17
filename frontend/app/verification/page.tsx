'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowClockwise, Copy, EnvelopeSimple, Trash, UploadSimple } from '@phosphor-icons/react';
import { stagger } from '@/components/AuthShell';
import { FormAlert } from '@/components/FormField';
import { SECTION_LABEL } from '@/components/home/Band';
import { BTN_DANGER_OUTLINE, BTN_OUTLINE, BTN_PRIMARY, CARD, EASE, PageHeader, PageSkeleton, Pill, SignInNotice } from '@/components/ui';
import { ApiError, messageFor } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { formatFingerprint } from '@/lib/keys';
import {
    buildMailto,
    checkProofFile,
    formatBytes,
    proof as proofApi,
    PROOF_MAX_BYTES,
    requests as requestsApi,
    SECRETARIAT_EMAILS,
    type GrantResult,
    type ProofInfo,
    type VerificationRequestItem,
} from '@/lib/verify';

function errText(e: unknown, fallback: string): string {
    return e instanceof ApiError ? messageFor(e.code, e.message) : fallback;
}

function formatDate(value: string): string {
    return new Date(value).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

function daysLeft(value: string): number {
    return Math.max(0, Math.ceil((Date.parse(value) - Date.now()) / 86_400_000));
}

/* ------------------------------------------------------------------ */
/* Proof upload                                                        */
/* ------------------------------------------------------------------ */

function ProofCard({ onChanged }: { onChanged: () => void }) {
    const [info, setInfo] = useState<ProofInfo | null>(null);
    const [loading, setLoading] = useState(true);
    const [file, setFile] = useState<File | null>(null);
    const [fileError, setFileError] = useState('');
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const [notice, setNotice] = useState('');
    const [fileKey, setFileKey] = useState(0);
    const inputRef = useRef<HTMLInputElement>(null);

    const load = useCallback(async () => {
        setLoading(true);
        setError('');
        try {
            setInfo(await proofApi.get());
        } catch (e) {
            if (e instanceof ApiError && e.status === 404) setInfo(null);
            else setError(errText(e, 'Could not load your proof.'));
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    async function pick(f: File | null) {
        setNotice('');
        setError('');
        setFile(null);
        setFileError('');
        if (!f) return;
        const problem = await checkProofFile(f);
        if (problem) {
            setFileError(problem);
            setFileKey((k) => k + 1);
            return;
        }
        setFile(f);
    }

    async function upload(e: React.FormEvent) {
        e.preventDefault();
        if (!file || busy) return;
        if (info && !window.confirm('Uploading a new proof replaces this one and ends any access you already gave. Continue?')) return;
        setBusy(true);
        setError('');
        setNotice('');
        try {
            setInfo(await proofApi.upload(file));
            setFile(null);
            setFileKey((k) => k + 1);
            setNotice('Proof uploaded.');
            onChanged();
        } catch (err) {
            setError(errText(err, 'The proof could not be uploaded. Try again.'));
        } finally {
            setBusy(false);
        }
    }

    async function remove() {
        if (!window.confirm('Delete your proof? Any access you already gave ends too.')) return;
        setBusy(true);
        setError('');
        setNotice('');
        try {
            await proofApi.remove();
            setInfo(null);
            setNotice('Proof deleted.');
            onChanged();
        } catch (err) {
            setError(errText(err, 'The proof could not be deleted.'));
        } finally {
            setBusy(false);
        }
    }

    return (
        <section className={`rise ${CARD}`} style={stagger(1)}>
            <p className={SECTION_LABEL}>Step 1</p>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight text-zinc-900">Your proof of alumni status</h2>
            <p className="mt-3 max-w-[60ch] text-sm leading-relaxed text-zinc-500">
                An alumni card, a diploma or a work letter. Only the admin you allow can read it, and it is deleted once the
                admin decides or after 14 days.
            </p>

            {loading ? (
                <div aria-hidden className="mt-6 h-16 animate-pulse rounded-2xl bg-zinc-200/60" />
            ) : info ? (
                <div className="mt-6 flex flex-wrap items-center justify-between gap-4 rounded-2xl bg-zinc-100 px-5 py-4">
                    <div className="min-w-0">
                        <p className="text-sm font-medium text-zinc-900">
                            <span className="uppercase">{info.ext}</span> · {formatBytes(info.size)}
                        </p>
                        <p className="mt-1 font-mono text-xs text-zinc-500">
                            Uploaded {formatDate(info.created_at)} · SHA-256 {info.sha256.slice(0, 12)}…
                        </p>
                    </div>
                    <button type="button" onClick={remove} disabled={busy} className={BTN_DANGER_OUTLINE}>
                        <Trash size={16} /> Delete
                    </button>
                </div>
            ) : (
                <p className="mt-6 rounded-2xl border border-dashed border-zinc-300 px-5 py-4 text-sm text-zinc-500">
                    No proof yet. Upload one so the admin can review it.
                </p>
            )}

            <form onSubmit={upload} className="mt-6 flex flex-col gap-4">
                <label
                    className={`flex cursor-pointer flex-col items-center gap-3 rounded-[2rem] border border-dashed border-zinc-300 bg-zinc-50/60 px-6 py-8 text-center transition duration-300 ${EASE} focus-within:border-zinc-900 focus-within:ring-4 focus-within:ring-zinc-900/10 hover:border-zinc-500`}
                >
                    <span className="grid h-12 w-12 place-items-center rounded-full bg-white text-zinc-800 shadow-[0_8px_20px_-8px_rgba(24,24,27,0.2)]">
                        <UploadSimple size={22} />
                    </span>
                    {file ? (
                        <span className="min-w-0 max-w-full">
                            <span className="block truncate text-sm font-medium text-zinc-900">{file.name}</span>
                            <span className="mt-0.5 block font-mono text-xs text-zinc-500">{formatBytes(file.size)}</span>
                        </span>
                    ) : (
                        <span className="text-sm text-zinc-600">
                            <span className="font-medium text-zinc-900">{info ? 'Choose a new file' : 'Choose a file'}</span> (PDF, JPG or PNG)
                        </span>
                    )}
                    <input
                        key={fileKey}
                        ref={inputRef}
                        className="sr-only"
                        type="file"
                        accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
                        onChange={(e) => pick(e.target.files?.[0] ?? null)}
                    />
                </label>
                {fileError ? (
                    <p role="alert" className="text-[13px] text-red-700">
                        {fileError}
                    </p>
                ) : (
                    <p className="text-[13px] text-zinc-500">Up to {formatBytes(PROOF_MAX_BYTES)}. One file; a new upload replaces the old one.</p>
                )}
                {error && <FormAlert>{error}</FormAlert>}
                <div className="flex flex-wrap items-center gap-4">
                    <button type="submit" disabled={!file || busy} className={BTN_PRIMARY}>
                        {busy ? 'Working…' : info ? 'Replace proof' : 'Upload proof'}
                    </button>
                    <p role="status" aria-live="polite" className="text-sm text-zinc-600">
                        {notice}
                    </p>
                </div>
            </form>
        </section>
    );
}

/* ------------------------------------------------------------------ */
/* One request                                                         */
/* ------------------------------------------------------------------ */

function CodePanel({ grant, adminUsername }: { grant: GrantResult; adminUsername: string }) {
    const [copied, setCopied] = useState(false);
    const mailto = buildMailto({ accessCode: grant.access_code, adminUsername, fingerprint: grant.admin_fingerprint });

    async function copy() {
        try {
            await navigator.clipboard.writeText(grant.access_code);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch {
            // No clipboard permission: select the text so Ctrl/Cmd+C works.
            document.getElementById(`code-${grant.request_id}`)?.focus();
        }
    }

    return (
        <div className="mt-5 rounded-2xl border border-zinc-900 p-5">
            <h4 className="text-sm font-semibold text-zinc-900">Send this access code to the secretariat</h4>
            <p className="mt-2 text-[13px] leading-relaxed text-zinc-600">
                It is shown only now. The code opens nothing without the admin&apos;s private key, but it has to reach them: send it from
                your own email app{SECRETARIAT_EMAILS.length > 0
                    ? '. The button fills in the secretariat\u2019s addresses for you.'
                    : ', to the secretariat\u2019s official address.'}
            </p>
            <textarea
                id={`code-${grant.request_id}`}
                readOnly
                rows={4}
                value={grant.access_code}
                onFocus={(e) => e.currentTarget.select()}
                className="mt-3 w-full rounded-2xl border border-zinc-200 bg-zinc-50 p-3 font-mono text-xs leading-relaxed text-zinc-800"
            />
            <div className="mt-3 flex flex-wrap gap-3">
                <a href={mailto} className={BTN_PRIMARY}>
                    <EnvelopeSimple size={16} /> Send by email
                </a>
                <button type="button" onClick={copy} className={BTN_OUTLINE}>
                    <Copy size={16} /> {copied ? 'Copied' : 'Copy code'}
                </button>
            </div>
            <p className="mt-3 text-[13px] text-zinc-500">
                No email app opens? Use Copy code and paste it into a message yourself, with the admin name and fingerprint below.
            </p>
        </div>
    );
}

function RequestCard({
    req,
    grant,
    onGranted,
}: {
    req: VerificationRequestItem;
    grant: GrantResult | undefined;
    onGranted: (g: GrantResult) => void;
}) {
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');

    async function allow() {
        setBusy(true);
        setError('');
        try {
            onGranted(await requestsApi.grant(req.id));
        } catch (e) {
            setError(errText(e, 'Access could not be given. Try again.'));
        } finally {
            setBusy(false);
        }
    }

    const fp = req.admin_fingerprint;
    return (
        <li className="rounded-[2rem] border border-zinc-200/70 bg-white p-6 shadow-[0_20px_40px_-15px_rgba(24,24,27,0.06)]">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                    <p className="text-lg font-semibold tracking-tight text-zinc-900">
                        Request from <span className="font-mono text-base">@{req.admin_username}</span>
                    </p>
                    <p className="mt-1 font-mono text-xs text-zinc-500">
                        Asked {formatDate(req.created_at)} · ends in {daysLeft(req.expires_at)} days
                    </p>
                </div>
                <Pill tone={req.status === 'granted' ? 'solid' : 'outline'}>{req.status === 'granted' ? 'Access given' : 'Waiting for you'}</Pill>
            </div>

            <div className="mt-4">
                <p className="text-[13px] font-medium text-zinc-900">Admin key fingerprint</p>
                {fp ? (
                    <code className="mt-2 block break-all rounded-2xl bg-zinc-100 px-4 py-3 font-mono text-xs leading-relaxed text-zinc-800">
                        {formatFingerprint(fp)}
                    </code>
                ) : (
                    <p className="mt-2 text-sm text-zinc-500">This admin has no active key now. Access cannot be given until they create one.</p>
                )}
                <p className="mt-2 text-[13px] text-zinc-500">
                    Compare it with the fingerprint the secretariat announced outside this site. If it differs, do not allow access.
                </p>
            </div>

            {req.status === 'pending' && !grant && (
                <div className="mt-5 flex flex-col items-start gap-3">
                    {error && <FormAlert>{error}</FormAlert>}
                    <button type="button" onClick={allow} disabled={busy || !fp} className={BTN_PRIMARY}>
                        {busy ? 'Giving access…' : 'Allow access'}
                    </button>
                </div>
            )}

            {grant && <CodePanel grant={grant} adminUsername={req.admin_username} />}
            {req.status === 'granted' && !grant && (
                <p className="mt-5 text-sm text-zinc-600">
                    Access was given and the code was shown once. If you did not send it, upload your proof again to start over.
                </p>
            )}
        </li>
    );
}

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

export default function VerificationPage() {
    const { user, loading } = useAuth();
    const [items, setItems] = useState<VerificationRequestItem[] | null>(null);
    const [error, setError] = useState('');
    // Access codes by request id. They live in memory only, because the server never stores them.
    const [grants, setGrants] = useState<Record<string, GrantResult>>({});

    const load = useCallback(async () => {
        setError('');
        try {
            setItems(await requestsApi.list());
        } catch (e) {
            setError(errText(e, 'Could not load your requests.'));
        }
    }, []);

    useEffect(() => {
        if (user?.role === 'alumni') load();
    }, [user, load]);

    if (loading) return <PageSkeleton />;
    if (!user) return <SignInNotice title="Verification">Sign in to upload your proof and answer admin requests.</SignInNotice>;
    if (user.role !== 'alumni') return <SignInNotice title="Verification">Only alumni accounts have a proof to verify.</SignInNotice>;

    return (
        <div className="flex flex-col gap-8">
            <PageHeader
                eyebrow="Alumni verification"
                title="Prove you are an alumnus"
                subtitle="Upload one document. An admin asks to see it, you allow it, and you send them a code by email."
            />

            <ProofCard
                onChanged={() => {
                    setGrants({});
                    load();
                }}
            />

            <section className="rise" style={stagger(2)}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                        <p className={SECTION_LABEL}>Step 2</p>
                        <h2 className="mt-3 text-2xl font-semibold tracking-tight text-zinc-900">Requests from admins</h2>
                    </div>
                    <button type="button" onClick={load} className={BTN_OUTLINE}>
                        <ArrowClockwise size={16} /> Refresh
                    </button>
                </div>

                {error && (
                    <div className="mt-6">
                        <FormAlert>{error}</FormAlert>
                    </div>
                )}
                {!items && !error && <div aria-hidden className="mt-6 h-40 animate-pulse rounded-[2rem] bg-zinc-200/60" />}
                {items && items.length === 0 && (
                    <p className="mt-6 rounded-[2rem] border border-dashed border-zinc-300 px-6 py-10 text-center text-sm text-zinc-500">
                        No admin has asked for your proof yet. Make sure it is uploaded, then check back here.
                    </p>
                )}
                {items && items.length > 0 && (
                    <ul className="mt-6 flex flex-col gap-3">
                        {items.map((r) => (
                            <RequestCard
                                key={r.id}
                                req={r}
                                grant={grants[r.id]}
                                onGranted={(g) => {
                                    setGrants((old) => ({ ...old, [r.id]: g }));
                                    load();
                                }}
                            />
                        ))}
                    </ul>
                )}
            </section>
        </div>
    );
}
