'use client';

import { useCallback, useEffect, useState } from 'react';
import { ArrowClockwise, DownloadSimple, Key, UploadSimple } from '@phosphor-icons/react';
import FormField, { FormAlert, inputClass } from '@/components/FormField';
import { SECTION_LABEL } from '@/components/home/Band';
import { BTN_OUTLINE, BTN_PRIMARY, CARD } from '@/components/ui';
import { ApiError, messageFor } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import {
    PASSPHRASE_MIN,
    createAdminKey,
    downloadBackup,
    formatFingerprint,
    getLocalKey,
    getServerKey,
    importBackup,
    KeysError,
    type BackupFile,
    type LocalKeyInfo,
    type ServerKey,
} from '@/lib/keys';

function errText(e: unknown, fallback: string): string {
    if (e instanceof KeysError) return e.message;
    if (e instanceof ApiError) return messageFor(e.code, e.message);
    return fallback;
}

function formatDate(value: string | null): string {
    if (!value) return 'Unknown';
    return new Date(value).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

function Badge({ children }: { children: React.ReactNode }) {
    return <span className="rounded-full border border-zinc-300 px-2.5 py-0.5 text-[11px] font-medium uppercase tracking-wider text-zinc-700">{children}</span>;
}

function Fingerprint({ hex }: { hex: string }) {
    return <code className="block break-all rounded-2xl bg-zinc-100 px-4 py-3 font-mono text-xs leading-relaxed text-zinc-800">{formatFingerprint(hex)}</code>;
}

export default function KeysTab() {
    const { user } = useAuth();
    const userId = user?.id ?? '';

    const [server, setServer] = useState<ServerKey | null>(null);
    const [local, setLocal] = useState<LocalKeyInfo | null>(null);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState<string | null>(null);

    // Create
    const [pass, setPass] = useState('');
    const [pass2, setPass2] = useState('');
    const [creating, setCreating] = useState(false);
    const [createError, setCreateError] = useState<string | null>(null);
    // The backup of a key that was just made. It is the only copy, so keep it on screen until it is saved.
    const [fresh, setFresh] = useState<BackupFile | null>(null);
    const [saved, setSaved] = useState(false);

    // Import
    const [file, setFile] = useState<File | null>(null);
    const [importPass, setImportPass] = useState('');
    const [importing, setImporting] = useState(false);
    const [importError, setImportError] = useState<string | null>(null);
    const [importNote, setImportNote] = useState<string | null>(null);

    const load = useCallback(async () => {
        if (!userId) return;
        setLoading(true);
        setLoadError(null);
        try {
            const [s, l] = await Promise.all([getServerKey(), getLocalKey(userId)]);
            setServer(s);
            setLocal(l);
        } catch (e) {
            setLoadError(errText(e, 'Could not load the key status.'));
        } finally {
            setLoading(false);
        }
    }, [userId]);

    useEffect(() => {
        load();
    }, [load]);

    const serverExpired = !!server && Date.parse(server.expires_at) <= Date.now();
    const inSync = !!server && !!local && server.fingerprint === local.fingerprint;

    const passError =
        pass && [...pass].length < PASSPHRASE_MIN
            ? `At least ${PASSPHRASE_MIN} characters.`
            : pass2 && pass !== pass2
              ? 'The passphrases do not match.'
              : undefined;
    const canCreate = !creating && [...pass].length >= PASSPHRASE_MIN && pass === pass2 && !fresh;

    async function onCreate(e: React.FormEvent) {
        e.preventDefault();
        if (!canCreate) return;
        if (
            server &&
            !window.confirm(
                'Creating a new key revokes your current key. Access you already granted for the old key will end. Continue?',
            )
        ) {
            return;
        }
        setCreating(true);
        setCreateError(null);
        try {
            const res = await createAdminKey(userId, pass);
            setFresh(res.backup);
            setSaved(false);
            setPass('');
            setPass2('');
            downloadBackup(res.backup);
            await load();
        } catch (err) {
            // The key exists on the server but is not stored here: still hand over the backup.
            if (err instanceof KeysError && err.backup) {
                setFresh(err.backup);
                setSaved(false);
            }
            setCreateError(errText(err, 'The key could not be created. Try again.'));
        } finally {
            setCreating(false);
        }
    }

    async function onImport(e: React.FormEvent) {
        e.preventDefault();
        if (!file || importing) return;
        setImporting(true);
        setImportError(null);
        setImportNote(null);
        try {
            const res = await importBackup(userId, file, importPass);
            setImportPass('');
            setFile(null);
            setImportNote(
                res.matchesServer === false
                    ? 'Restored in this browser, but it is not the key the server currently uses. Requests are wrapped for the server key.'
                    : 'Key restored. This browser can open proofs again.',
            );
            await load();
        } catch (err) {
            setImportError(errText(err, 'The backup could not be imported.'));
        } finally {
            setImporting(false);
        }
    }

    if (loading && !server && !local) {
        return <div aria-hidden className="mt-6 h-48 animate-pulse rounded-[2rem] bg-zinc-200/60" />;
    }

    return (
        <div className="mt-6 flex flex-col gap-6">
            {loadError && (
                <div className="flex flex-col gap-3">
                    <FormAlert>{loadError}</FormAlert>
                    <button type="button" onClick={load} className={`${BTN_OUTLINE} self-start`}>
                        <ArrowClockwise size={16} /> Retry
                    </button>
                </div>
            )}

            <section className={CARD}>
                <p className={SECTION_LABEL}>Proof key</p>
                <h2 className="mt-3 text-2xl font-semibold tracking-tight text-zinc-900">Your admin key</h2>
                <p className="mt-3 max-w-[60ch] text-sm leading-relaxed text-zinc-500">
                    Alumni lock proofs for you with this key. The private half stays in this browser and never goes to the
                    server. Tell the secretariat your fingerprint so alumni can check it.
                </p>

                <div className="mt-6 grid gap-6 md:grid-cols-2">
                    <div>
                        <div className="flex items-center gap-2">
                            <h3 className="text-sm font-medium text-zinc-900">Registered on the server</h3>
                            {server && <Badge>{serverExpired ? 'Expired' : 'Active'}</Badge>}
                        </div>
                        {server ? (
                            <>
                                <div className="mt-3">
                                    <Fingerprint hex={server.fingerprint} />
                                </div>
                                <p className="mt-2 text-[13px] text-zinc-500">Expires {formatDate(server.expires_at)}</p>
                            </>
                        ) : (
                            <p className="mt-3 text-sm text-zinc-500">No active key. Alumni cannot be asked for proofs until you create one.</p>
                        )}
                    </div>

                    <div>
                        <div className="flex items-center gap-2">
                            <h3 className="text-sm font-medium text-zinc-900">Stored in this browser</h3>
                            {local && server && <Badge>{inSync ? 'Matches' : 'Different key'}</Badge>}
                        </div>
                        {local ? (
                            <>
                                <div className="mt-3">
                                    <Fingerprint hex={local.fingerprint} />
                                </div>
                                {!inSync && server && (
                                    <p className="mt-2 text-[13px] text-red-700">
                                        This is not the key the server uses. Import the matching backup or create a new key.
                                    </p>
                                )}
                            </>
                        ) : (
                            <p className="mt-3 text-sm text-zinc-500">
                                No private key here. {server ? 'Import your backup to open proofs on this browser.' : 'Create a key or import a backup.'}
                            </p>
                        )}
                    </div>
                </div>
            </section>

            {fresh && (
                <section className={`${CARD} border-zinc-900`}>
                    <h2 className="text-xl font-semibold tracking-tight text-zinc-900">Keep your backup file</h2>
                    <p className="mt-3 max-w-[60ch] text-sm leading-relaxed text-zinc-600">
                        The backup was downloaded as a <code>.tcancykey</code> file. It is the only way to restore this key if
                        this browser is cleared. Store it somewhere safe, and remember the passphrase: it cannot be recovered.
                    </p>
                    <div className="mt-5 flex flex-wrap items-center gap-3">
                        <button type="button" onClick={() => downloadBackup(fresh)} className={BTN_OUTLINE}>
                            <DownloadSimple size={16} /> Download again
                        </button>
                        <label className="flex items-center gap-2 text-sm text-zinc-700">
                            <input type="checkbox" checked={saved} onChange={(e) => setSaved(e.target.checked)} className="size-4" />
                            I saved the backup file
                        </label>
                        <button type="button" disabled={!saved} onClick={() => setFresh(null)} className={BTN_PRIMARY}>
                            Done
                        </button>
                    </div>
                </section>
            )}

            <section className={CARD}>
                <h2 className="flex items-center gap-2 text-xl font-semibold tracking-tight text-zinc-900">
                    <Key size={20} /> {server ? 'Create a new key' : 'Create your key'}
                </h2>
                <p className="mt-3 max-w-[60ch] text-sm leading-relaxed text-zinc-500">
                    The passphrase protects the backup file. A new key lasts one year and replaces the old one.
                </p>
                <form onSubmit={onCreate} className="mt-6 grid max-w-xl gap-4">
                    <FormField label="Backup passphrase" hint={`At least ${PASSPHRASE_MIN} characters.`} error={passError}>
                        <input
                            type="password"
                            autoComplete="new-password"
                            value={pass}
                            onChange={(e) => setPass(e.target.value)}
                            className={inputClass}
                        />
                    </FormField>
                    <FormField label="Repeat passphrase">
                        <input
                            type="password"
                            autoComplete="new-password"
                            value={pass2}
                            onChange={(e) => setPass2(e.target.value)}
                            className={inputClass}
                        />
                    </FormField>
                    {createError && <FormAlert>{createError}</FormAlert>}
                    <button type="submit" disabled={!canCreate} className={`${BTN_PRIMARY} self-start`}>
                        {creating ? 'Creating key…' : 'Create key and download backup'}
                    </button>
                </form>
            </section>

            <section className={CARD}>
                <h2 className="flex items-center gap-2 text-xl font-semibold tracking-tight text-zinc-900">
                    <UploadSimple size={20} /> Restore from backup
                </h2>
                <p className="mt-3 max-w-[60ch] text-sm leading-relaxed text-zinc-500">
                    Use this on a new browser or after clearing site data. The restored fingerprint must match the one in the file.
                </p>
                <form onSubmit={onImport} className="mt-6 grid max-w-xl gap-4">
                    <FormField label="Backup file (.tcancykey)">
                        <input
                            type="file"
                            accept=".tcancykey,application/json"
                            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                            className="text-sm text-zinc-700 file:mr-4 file:rounded-full file:border-0 file:bg-zinc-100 file:px-4 file:py-2 file:text-sm file:font-medium"
                        />
                    </FormField>
                    <FormField label="Passphrase">
                        <input
                            type="password"
                            autoComplete="current-password"
                            value={importPass}
                            onChange={(e) => setImportPass(e.target.value)}
                            className={inputClass}
                        />
                    </FormField>
                    {importError && <FormAlert>{importError}</FormAlert>}
                    {importNote && <p className="text-sm text-zinc-700">{importNote}</p>}
                    <button type="submit" disabled={!file || importing || !importPass} className={`${BTN_OUTLINE} self-start`}>
                        {importing ? 'Restoring…' : 'Restore key'}
                    </button>
                </form>
            </section>
        </div>
    );
}
