'use client';

import { useEffect, useRef, useState } from 'react';
import { FileMagnifyingGlass, LockKeyOpen, PaperPlaneTilt, X } from '@phosphor-icons/react';
import { FormAlert, textareaClass } from '@/components/FormField';
import { BTN_OUTLINE, BTN_PRIMARY } from '@/components/ui';
import { ApiError, messageFor } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { KeysError } from '@/lib/keys';
import { openProof, ProofCryptoError, type OpenedProof } from '@/lib/proofcrypto';
import { formatBytes, requestProof, saveRequest, savedRequests } from '@/lib/verify';

function errText(e: unknown, fallback: string): string {
    if (e instanceof KeysError || e instanceof ProofCryptoError) return e.message;
    if (e instanceof ApiError) return messageFor(e.code, e.message);
    return fallback;
}

/**
 * The proof step of reviewing a pending alumnus: ask for it, then open it in this browser.
 * Opening needs the private key stored here and the access code the alumnus sent by email.
 * The decrypted file only exists as a blob URL on this page; closing the panel drops it.
 */
export default function ProofPanel({ alumniId, username }: { alumniId: string; username: string }) {
    const { user } = useAuth();
    const adminId = user?.id ?? '';

    const [requestId, setRequestId] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const [notice, setNotice] = useState('');
    const [showOpen, setShowOpen] = useState(false);
    const [code, setCode] = useState('');
    const [opened, setOpened] = useState<(OpenedProof & { url: string }) | null>(null);
    const [needsKey, setNeedsKey] = useState(false);
    const urlRef = useRef<string | null>(null);

    useEffect(() => {
        if (adminId) setRequestId(savedRequests(adminId)[alumniId] ?? null);
    }, [adminId, alumniId]);

    // Never leave a decrypted proof behind when the panel goes away.
    useEffect(
        () => () => {
            if (urlRef.current) URL.revokeObjectURL(urlRef.current);
        },
        [],
    );

    function closeProof() {
        if (urlRef.current) URL.revokeObjectURL(urlRef.current);
        urlRef.current = null;
        setOpened(null);
        setShowOpen(false);
        setCode('');
    }

    async function ask() {
        setBusy(true);
        setError('');
        setNotice('');
        try {
            const req = await requestProof(alumniId);
            saveRequest(adminId, alumniId, req.id);
            setRequestId(req.id);
            setNotice(`Asked @${username} for their proof. When they allow it, they send you an access code by email.`);
        } catch (e) {
            if (e instanceof ApiError && e.code === 'NO_PUBLIC_KEY') setNeedsKey(true);
            setError(
                e instanceof ApiError && e.code === 'REQUEST_EXISTS'
                    ? 'You already asked this alumnus, but this browser does not remember the request. Ask them to upload their proof again, which ends the old request.'
                    : errText(e, 'Could not ask for the proof.'),
            );
        } finally {
            setBusy(false);
        }
    }

    async function open(e: React.FormEvent) {
        e.preventDefault();
        if (!requestId || !code.trim() || busy) return;
        setBusy(true);
        setError('');
        setNeedsKey(false);
        try {
            const res = await openProof(adminId, requestId, code);
            const url = URL.createObjectURL(new Blob([res.bytes as unknown as BlobPart], { type: res.mime }));
            if (urlRef.current) URL.revokeObjectURL(urlRef.current);
            urlRef.current = url;
            setOpened({ ...res, url });
            setCode('');
        } catch (err) {
            if (err instanceof KeysError || (err instanceof ProofCryptoError && err.code === 'KEY_MISMATCH')) setNeedsKey(true);
            if (err instanceof ApiError && err.status === 410) {
                saveRequest(adminId, alumniId, null);
                setRequestId(null);
                setShowOpen(false);
            }
            setError(errText(err, 'The proof could not be opened.'));
        } finally {
            setBusy(false);
        }
    }

    return (
        <div className="mt-5 rounded-2xl bg-zinc-50 p-5">
            <h4 className="flex items-center gap-2 text-sm font-semibold text-zinc-900">
                <FileMagnifyingGlass size={18} /> Proof of alumni status
            </h4>
            <p className="mt-2 text-[13px] leading-relaxed text-zinc-500">
                Review the proof before you decide. Approving or rejecting without opening it is refused.
            </p>

            {notice && (
                <p role="status" className="mt-3 text-sm text-zinc-700">
                    {notice}
                </p>
            )}
            {error && (
                <div className="mt-3 flex flex-col items-start gap-2">
                    <FormAlert>{error}</FormAlert>
                    {needsKey && (
                        <p className="text-[13px] text-zinc-600">
                            Manage your key in the <span className="font-medium">Proof key</span> tab of this page.
                        </p>
                    )}
                </div>
            )}

            {!requestId && (
                <div className="mt-4">
                    <button type="button" onClick={ask} disabled={busy} className={BTN_OUTLINE}>
                        <PaperPlaneTilt size={16} /> {busy ? 'Asking…' : 'Ask for proof'}
                    </button>
                </div>
            )}

            {requestId && !opened && !showOpen && (
                <div className="mt-4 flex flex-wrap items-center gap-3">
                    <button type="button" onClick={() => setShowOpen(true)} className={BTN_PRIMARY}>
                        <LockKeyOpen size={16} /> Open proof
                    </button>
                    <span className="text-[13px] text-zinc-500">Needs the access code @{username} sends you.</span>
                </div>
            )}

            {requestId && !opened && showOpen && (
                <form onSubmit={open} className="mt-4 flex max-w-xl flex-col gap-3">
                    <label className="flex flex-col gap-2 text-sm">
                        <span className="font-medium text-zinc-900">Access code</span>
                        <textarea
                            value={code}
                            onChange={(e) => setCode(e.target.value)}
                            rows={4}
                            spellCheck={false}
                            autoComplete="off"
                            placeholder="Paste the code from the email"
                            className={`${textareaClass} font-mono text-xs`}
                        />
                    </label>
                    <div className="flex flex-wrap gap-3">
                        <button type="submit" disabled={busy || !code.trim()} className={BTN_PRIMARY}>
                            {busy ? 'Opening…' : 'Decrypt and view'}
                        </button>
                        <button type="button" onClick={() => setShowOpen(false)} className={BTN_OUTLINE}>
                            Cancel
                        </button>
                    </div>
                </form>
            )}

            {opened && (
                <div className="mt-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                        <p className="font-mono text-xs text-zinc-500">
                            {opened.ext.toUpperCase()} · {formatBytes(opened.bytes.length)} · decrypted in this browser only
                        </p>
                        <button type="button" onClick={closeProof} className={BTN_OUTLINE}>
                            <X size={16} /> Close proof
                        </button>
                    </div>
                    <div className="mt-3 overflow-hidden rounded-2xl border border-zinc-200 bg-white">
                        {opened.ext === 'pdf' ? (
                            <iframe src={opened.url} title={`Proof from @${username}`} className="h-[32rem] w-full" />
                        ) : (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img src={opened.url} alt={`Proof from @${username}`} className="mx-auto max-h-[32rem] w-auto" />
                        )}
                    </div>
                    <p className="mt-3 text-[13px] text-zinc-500">You can now approve or reject. Copies you save yourself are outside this site&apos;s control.</p>
                </div>
            )}
        </div>
    );
}
