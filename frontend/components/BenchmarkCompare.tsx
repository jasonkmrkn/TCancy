'use client';

import { useEffect, useState } from 'react';
import { Check, Play } from '@phosphor-icons/react';
import { FormAlert, inputClass } from '@/components/FormField';
import { SECTION_LABEL } from '@/components/home/Band';
import AlgorithmChart, { parseAlgorithms } from '@/components/AlgorithmChart';
import { fetchCiphertext, PREVIEW_BYTES, type Cipher } from '@/lib/ciphertext';
import { JsonView, cap, formatBytes } from '@/components/JsonView';
import { BTN_OUTLINE, BTN_PRIMARY, CARD, EASE } from '@/components/ui';
import { ApiError, messageFor } from '@/lib/api';
import { documents, type DocumentItem } from '@/lib/endpoints';

const TYPE_LABEL: Record<string, string> = { cv: 'CV', ktp: 'ID card', intro_video: 'Intro video' };

type Outcome = { doc: DocumentItem; data?: unknown; error?: string };

const isObject = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const isScalar = (v: unknown) => ['number', 'string', 'boolean'].includes(typeof v);

/** Top-level scalar fields of a result, plus scalar fields of nested objects as "parent.child". */
function flatten(data: unknown): Record<string, string | number | boolean> {
    const out: Record<string, string | number | boolean> = {};
    if (!isObject(data)) return out;
    for (const [k, v] of Object.entries(data)) {
        if (isScalar(v)) out[k] = v as string | number | boolean;
        else if (isObject(v)) {
            for (const [k2, v2] of Object.entries(v)) if (isScalar(v2)) out[`${k}.${k2}`] = v2 as string | number | boolean;
        }
    }
    return out;
}

function cell(key: string, v: string | number | boolean | undefined): string {
    if (v === undefined) return '—';
    if (typeof v === 'number') {
        if (/(^|[._])(size|bytes)(_bytes)?$/i.test(key) && Number.isInteger(v)) return formatBytes(v);
        return Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, { maximumFractionDigits: 4 });
    }
    if (typeof v === 'boolean') return v ? 'Yes' : 'No';
    return v;
}

function errText(e: unknown, fallback: string): string {
    return e instanceof ApiError ? messageFor(e.code, e.message) : fallback;
}

function CipherView({ docId }: { docId: string }) {
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const [cipher, setCipher] = useState<Cipher | null>(null);

    async function load() {
        setBusy(true);
        setError('');
        try {
            setCipher(await fetchCiphertext(docId));
        } catch (e) {
            setError(errText(e, 'Could not load the ciphertext.'));
        } finally {
            setBusy(false);
        }
    }

    const pre = 'mt-4 max-h-64 overflow-auto break-all whitespace-pre-wrap rounded-2xl bg-zinc-950 p-4 font-mono text-xs leading-relaxed text-zinc-200';
    return (
        <div>
            <button type="button" onClick={load} disabled={busy} className={BTN_OUTLINE}>
                {busy ? 'Loading...' : cipher ? 'Reload ciphertext' : 'Show ciphertext'}
            </button>
            {error && (
                <div className="mt-3">
                    <FormAlert>{error}</FormAlert>
                </div>
            )}
            {cipher?.kind === 'json' && (
                <div className="mt-4">
                    <JsonView value={cipher.value} />
                </div>
            )}
            {cipher?.kind === 'text' && <pre className={pre}>{cipher.value}</pre>}
            {cipher?.kind === 'binary' && (
                <>
                    <p className="mt-4 font-mono text-xs text-zinc-500">
                        {formatBytes(cipher.size)}
                        {cipher.truncated ? ` · first ${PREVIEW_BYTES} bytes shown` : ''}
                    </p>
                    <pre className={pre.replace('mt-4', 'mt-2')}>{cipher.hex}</pre>
                </>
            )}
        </div>
    );
}

function Result({ data }: { data: unknown }) {
    const parsed = parseAlgorithms(data);
    return (
        <div className="flex flex-col gap-4">
            {parsed ? <AlgorithmChart algos={parsed.algos} meta={parsed.meta} /> : <JsonView value={data} />}
            {parsed && (
                <details className="text-sm">
                    <summary className="cursor-pointer select-none font-medium text-zinc-600 hover:text-zinc-900">Raw JSON</summary>
                    <pre className="mt-3 max-h-64 overflow-auto rounded-2xl bg-zinc-950 p-4 font-mono text-xs leading-relaxed text-zinc-200">
                        {JSON.stringify(data, null, 2)}
                    </pre>
                </details>
            )}
        </div>
    );
}

export default function BenchmarkCompare() {
    const [docs, setDocs] = useState<DocumentItem[] | null>(null);
    const [loadError, setLoadError] = useState('');
    const [picked, setPicked] = useState<string[]>([]);
    const [repeats, setRepeats] = useState('5');
    const [repeatsError, setRepeatsError] = useState('');
    const [pickError, setPickError] = useState('');
    const [running, setRunning] = useState(false);
    const [progress, setProgress] = useState('');
    const [results, setResults] = useState<Outcome[] | null>(null);

    useEffect(() => {
        documents
            .list()
            .then((d) => setDocs(d))
            .catch((e) => {
                setDocs([]);
                setLoadError(errText(e, 'Could not load your documents.'));
            });
    }, []);

    function toggle(id: string) {
        setPickError('');
        setPicked((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));
    }

    async function run(e: React.FormEvent) {
        e.preventDefault();
        const n = Number(repeats);
        let bad = false;
        if (!Number.isInteger(n) || n < 1) {
            setRepeatsError('Repeats must be a whole number, at least 1.');
            bad = true;
        } else setRepeatsError('');
        if (picked.length === 0) {
            setPickError('Choose at least one file.');
            bad = true;
        }
        if (bad || !docs) return;

        const chosen = docs.filter((d) => picked.includes(d.id));
        setRunning(true);
        setResults(null);
        const out: Outcome[] = [];
        for (let i = 0; i < chosen.length; i++) {
            setProgress(`Running ${i + 1} of ${chosen.length}`);
            try {
                out.push({ doc: chosen[i], data: await documents.benchmark(chosen[i].id, n) });
            } catch (err) {
                out.push({ doc: chosen[i], error: errText(err, 'The benchmark failed.') });
            }
        }
        setResults(out);
        setRunning(false);
        setProgress('');
    }

    const ok = (results ?? []).filter((r) => r.data !== undefined);
    const flat = ok.map((r) => flatten(r.data));
    const cols: string[] = [];
    for (const f of flat) for (const k of Object.keys(f)) if (!cols.includes(k)) cols.push(k);

    return (
        <section className={`${CARD} flex flex-col gap-8`} aria-label="Encryption benchmark">
            <div>
                <h2 className={SECTION_LABEL}>Encryption benchmark</h2>
                <p className="mt-3 max-w-[60ch] text-zinc-500">
                    Pick one or more of your files and measure how long encrypting each takes. With several files selected, the results
                    are shown side by side.
                </p>
            </div>

            {!docs ? (
                <div aria-hidden className="h-32 animate-pulse rounded-2xl bg-zinc-200/60" />
            ) : docs.length === 0 ? (
                <p className="rounded-2xl border border-dashed border-zinc-300 px-6 py-6 text-zinc-500">
                    {loadError || 'You have no files yet. Upload one in Documents first.'}
                </p>
            ) : (
                <form onSubmit={run} noValidate className="flex flex-col gap-6">
                    <fieldset className="flex flex-col gap-2 text-sm" data-invalid={pickError ? 'true' : undefined}>
                        <div className="flex items-baseline justify-between">
                            <legend className="font-medium text-zinc-900">Files</legend>
                            <span className="font-mono text-xs text-zinc-500">{picked.length} selected</span>
                        </div>
                        <div className="grid gap-2 sm:grid-cols-2">
                            {docs.map((d) => {
                                const on = picked.includes(d.id);
                                return (
                                    <label
                                        key={d.id}
                                        className={`flex cursor-pointer items-center gap-3 rounded-2xl border px-4 py-3 transition duration-300 ${EASE} focus-within:ring-4 focus-within:ring-zinc-900/10 ${on ? 'border-zinc-900 bg-zinc-50' : 'border-zinc-200 bg-white hover:border-zinc-400'
                                            }`}
                                    >
                                        <input type="checkbox" className="sr-only" checked={on} onChange={() => toggle(d.id)} />
                                        <span
                                            aria-hidden
                                            className={`grid h-5 w-5 shrink-0 place-items-center rounded-md border ${on ? 'border-zinc-900 bg-zinc-900 text-zinc-50' : 'border-zinc-300 bg-white'
                                                }`}
                                        >
                                            {on && <Check size={12} weight="bold" />}
                                        </span>
                                        <span className="min-w-0 flex-1">
                                            <span className="block font-medium text-zinc-900">
                                                {TYPE_LABEL[d.type] ?? d.type} ·{' '}
                                                {new Date(d.created_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}
                                            </span>
                                            <span className="block font-mono text-xs text-zinc-500">
                                                {d.ext.replace(/^\./, '').toUpperCase()} · {formatBytes(d.size)}
                                            </span>
                                        </span>
                                    </label>
                                );
                            })}
                        </div>
                        {pickError && (
                            <p role="alert" className="text-[13px] text-red-700">
                                {pickError}
                            </p>
                        )}
                    </fieldset>

                    <div className="flex flex-wrap items-end gap-4">
                        <label className="flex w-40 flex-col gap-2 text-sm">
                            <span className="font-medium text-zinc-900">Repeats</span>
                            <input
                                className={inputClass}
                                type="number"
                                min={1}
                                inputMode="numeric"
                                value={repeats}
                                onChange={(e) => {
                                    setRepeats(e.target.value);
                                    setRepeatsError('');
                                }}
                            />
                        </label>
                        <button type="submit" disabled={running} className={`${BTN_PRIMARY} !min-h-14`}>
                            <Play size={16} weight="fill" />
                            {running ? progress || 'Running...' : 'Run benchmark'}
                        </button>
                    </div>
                    {repeatsError && (
                        <p role="alert" className="-mt-3 text-[13px] text-red-700">
                            {repeatsError}
                        </p>
                    )}
                </form>
            )}

            {results && (
                <div className="flex flex-col gap-8">
                    {ok.length > 1 && cols.length > 0 && ok.some((r) => !parseAlgorithms(r.data)) && (
                        <div>
                            <h3 className={SECTION_LABEL}>Comparison</h3>
                            <div className="mt-4 overflow-x-auto rounded-2xl border border-zinc-200">
                                <table className="w-full min-w-max text-left text-sm">
                                    <thead className="bg-zinc-50 font-mono text-xs uppercase tracking-wider text-zinc-500">
                                        <tr>
                                            <th className="px-4 py-3 font-medium">File</th>
                                            {cols.map((c) => (
                                                <th key={c} className="px-4 py-3 font-medium">
                                                    {cap(c.replace(/\./g, ' '))}
                                                </th>
                                            ))}
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-zinc-200">
                                        {ok.map((r, i) => (
                                            <tr key={r.doc.id}>
                                                <td className="px-4 py-3 font-medium text-zinc-900">
                                                    {TYPE_LABEL[r.doc.type] ?? r.doc.type}
                                                    <span className="ml-2 font-mono text-xs font-normal text-zinc-500">{formatBytes(r.doc.size)}</span>
                                                </td>
                                                {cols.map((c) => (
                                                    <td key={c} className="px-4 py-3 font-mono tabular-nums text-zinc-800">
                                                        {cell(c, flat[i][c])}
                                                    </td>
                                                ))}
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}

                    <div>
                        <h3 className={SECTION_LABEL}>Details</h3>
                        <ul className="mt-4 divide-y divide-zinc-200 border-y border-zinc-200">
                            {results.map((r) => (
                                <li key={r.doc.id} className="py-5">
                                    <details open>
                                        <summary className="cursor-pointer select-none font-medium text-zinc-900">
                                            {TYPE_LABEL[r.doc.type] ?? r.doc.type}
                                            <span className="ml-2 font-mono text-xs font-normal text-zinc-500">
                                                {r.doc.ext.replace(/^\./, '').toUpperCase()} · {formatBytes(r.doc.size)}
                                            </span>
                                        </summary>
                                        <div className="mt-5 flex flex-col gap-6">
                                            {r.error ? <FormAlert>{r.error}</FormAlert> : <Result data={r.data} />}
                                            <CipherView docId={r.doc.id} />
                                        </div>
                                    </details>
                                </li>
                            ))}
                        </ul>
                    </div>
                </div>
            )}
        </section>
    );
}