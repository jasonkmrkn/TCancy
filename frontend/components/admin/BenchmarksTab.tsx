'use client';

import { useCallback, useEffect, useState } from 'react';
import { ArrowClockwise, Plus, Play } from '@phosphor-icons/react';
import Chip from '@/components/Chip';
import FormField, { FormAlert, inputClass } from '@/components/FormField';
import { SECTION_LABEL } from '@/components/home/Band';
import { BTN_OUTLINE, BTN_PRIMARY, CARD } from '@/components/ui';
import { ApiError, messageFor } from '@/lib/api';
import { admin } from '@/lib/endpoints';

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

const PRESETS = [1024, 16384, 65536, 262144, 1048576];
const DEFAULT_SIZES = [1024, 65536, 1048576];

function formatBytes(n: number): string {
    if (n >= 1024 * 1024 && n % (1024 * 1024) === 0) return `${n / (1024 * 1024)} MB`;
    if (n >= 1024 && n % 1024 === 0) return `${n / 1024} KB`;
    return `${n.toLocaleString()} B`;
}

const cap = (s: string) => {
    const t = s.replace(/_/g, ' ');
    return t.charAt(0).toUpperCase() + t.slice(1);
};

function errText(e: unknown, fallback: string): string {
    return e instanceof ApiError ? messageFor(e.code, e.message) : fallback;
}

const isObject = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const isSizeKey = (k: string) => /(^|_)(size|bytes)(_bytes)?$/i.test(k);

function formatValue(key: string, v: unknown): string {
    if (v === null || v === undefined) return '—';
    if (typeof v === 'number') {
        if (isSizeKey(key) && Number.isInteger(v) && v >= 0) return formatBytes(v);
        return Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, { maximumFractionDigits: 4 });
    }
    if (typeof v === 'boolean') return v ? 'Yes' : 'No';
    if (typeof v === 'string') return v;
    return JSON.stringify(v);
}

/* ------------------------------------------------------------------ */
/* Generic JSON renderer (the backend does not type these responses)   */
/* ------------------------------------------------------------------ */

function Table({ rows }: { rows: Record<string, unknown>[] }) {
    const cols: string[] = [];
    for (const r of rows) for (const k of Object.keys(r)) if (!cols.includes(k)) cols.push(k);
    return (
        <div className="overflow-x-auto rounded-2xl border border-zinc-200">
            <table className="w-full min-w-max text-left text-sm">
                <thead>
                    <tr className="border-b border-zinc-200 bg-zinc-50">
                        {cols.map((c) => (
                            <th key={c} scope="col" className="whitespace-nowrap px-4 py-3 text-xs font-semibold uppercase tracking-wider text-zinc-500">
                                {cap(c)}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody className="divide-y divide-zinc-100">
                    {rows.map((r, i) => (
                        <tr key={i}>
                            {cols.map((c) => (
                                <td key={c} className="whitespace-nowrap px-4 py-3 font-mono text-[13px] tabular-nums text-zinc-800">
                                    {formatValue(c, r[c])}
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

function JsonView({ value, name = '', depth = 0 }: { value: unknown; name?: string; depth?: number }) {
    if (Array.isArray(value)) {
        if (value.length === 0) return <p className="text-sm text-zinc-500">No results.</p>;
        if (value.every(isObject)) return <Table rows={value as Record<string, unknown>[]} />;
        return (
            <ul className="flex flex-wrap gap-2">
                {value.map((v, i) => (
                    <li key={i} className="rounded-full bg-zinc-100 px-3 py-1 font-mono text-xs text-zinc-700">
                        {formatValue(name, v)}
                    </li>
                ))}
            </ul>
        );
    }

    if (isObject(value)) {
        const entries = Object.entries(value);
        const scalars = entries.filter(([, v]) => !Array.isArray(v) && !isObject(v));
        const complex = entries.filter(([, v]) => Array.isArray(v) || isObject(v));
        return (
            <div className="flex flex-col gap-6">
                {scalars.length > 0 && (
                    <dl className="grid grid-cols-2 gap-3 md:grid-cols-3">
                        {scalars.map(([k, v]) => (
                            <div key={k} className="rounded-2xl bg-zinc-50 px-4 py-3">
                                <dt className="text-xs uppercase tracking-wider text-zinc-500">{cap(k)}</dt>
                                <dd className="mt-1 break-words font-mono text-sm font-semibold tabular-nums text-zinc-900">{formatValue(k, v)}</dd>
                            </div>
                        ))}
                    </dl>
                )}
                {complex.map(([k, v]) => (
                    <div key={k}>
                        <h4 className={`${SECTION_LABEL} mb-3`}>{cap(k)}</h4>
                        {depth >= 3 ? (
                            <pre className="overflow-x-auto rounded-2xl bg-zinc-50 p-4 font-mono text-xs text-zinc-700">{JSON.stringify(v, null, 2)}</pre>
                        ) : (
                            <JsonView value={v} name={k} depth={depth + 1} />
                        )}
                    </div>
                ))}
            </div>
        );
    }

    return <p className="font-mono text-sm text-zinc-800">{formatValue(name, value)}</p>;
}

function ResultCard({
    title,
    value,
    action,
    footnote,
}: {
    title: string;
    value: unknown;
    action?: React.ReactNode;
    footnote?: string;
}) {
    return (
        <section className={CARD} aria-label={title}>
            <div className="flex flex-wrap items-center justify-between gap-4">
                <h2 className="text-2xl font-semibold tracking-tight text-zinc-900">{title}</h2>
                {action}
            </div>
            {footnote && <p className="mt-1 text-sm text-zinc-500">{footnote}</p>}
            <div className="mt-6">
                {value === null || value === undefined || value === '' ? (
                    <p className="text-zinc-500">Nothing to show yet.</p>
                ) : (
                    <JsonView value={value} />
                )}
            </div>
            {value !== null && value !== undefined && typeof value === 'object' && (
                <details className="mt-6 text-sm">
                    <summary className="cursor-pointer select-none font-medium text-zinc-600 hover:text-zinc-900">Raw JSON</summary>
                    <pre className="mt-3 max-h-80 overflow-auto rounded-2xl bg-zinc-950 p-4 font-mono text-xs leading-relaxed text-zinc-200">
                        {JSON.stringify(value, null, 2)}
                    </pre>
                </details>
            )}
        </section>
    );
}

/* ------------------------------------------------------------------ */
/* Tab                                                                 */
/* ------------------------------------------------------------------ */

export default function BenchmarksTab() {
    const [sizes, setSizes] = useState<number[]>(DEFAULT_SIZES);
    const [custom, setCustom] = useState<number[]>([]);
    const [customInput, setCustomInput] = useState('');
    const [repeats, setRepeats] = useState('3');
    const [errors, setErrors] = useState<Record<string, string>>({});
    const [running, setRunning] = useState(false);
    const [runError, setRunError] = useState('');
    const [result, setResult] = useState<unknown>(null);
    const [ranAt, setRanAt] = useState<Date | null>(null);

    const [summary, setSummary] = useState<unknown>(null);
    const [summaryState, setSummaryState] = useState<'loading' | 'ready' | 'error'>('loading');
    const [summaryError, setSummaryError] = useState('');

    const loadSummary = useCallback(() => {
        setSummaryState('loading');
        setSummaryError('');
        admin
            .benchmarks()
            .then((s) => {
                setSummary(s);
                setSummaryState('ready');
            })
            .catch((e) => {
                setSummaryError(errText(e, 'Could not load the benchmark summary.'));
                setSummaryState('error');
            });
    }, []);

    useEffect(loadSummary, [loadSummary]);

    const options = [...PRESETS, ...custom.filter((c) => !PRESETS.includes(c))];

    function toggle(size: number) {
        setErrors((e) => ({ ...e, sizes: '' }));
        setSizes((cur) => (cur.includes(size) ? cur.filter((s) => s !== size) : [...cur, size]));
    }

    function addCustom() {
        const n = Number(customInput);
        if (!Number.isInteger(n) || n < 1) {
            setErrors((e) => ({ ...e, custom: 'Enter a whole number of bytes, at least 1.' }));
            return;
        }
        setErrors((e) => ({ ...e, custom: '', sizes: '' }));
        if (!options.includes(n)) setCustom((c) => [...c, n]);
        setSizes((cur) => (cur.includes(n) ? cur : [...cur, n]));
        setCustomInput('');
    }

    async function run(e: React.FormEvent) {
        e.preventDefault();
        setRunError('');
        const found: Record<string, string> = {};
        const reps = Number(repeats);
        if (sizes.length === 0) found.sizes = 'Choose at least one size.';
        if (!Number.isInteger(reps) || reps < 1) found.repeats = 'Repeats must be a whole number, at least 1.';
        setErrors(found);
        if (Object.keys(found).length > 0) return;

        setRunning(true);
        try {
            const res = await admin.runBenchmark({ sizes: [...sizes].sort((a, b) => a - b), repeats: reps });
            setResult(res);
            setRanAt(new Date());
            loadSummary();
        } catch (err) {
            if (err instanceof ApiError && Object.keys(err.fields).length > 0) {
                setErrors({ sizes: err.fields.sizes ?? '', repeats: err.fields.repeats ?? '' });
            }
            setRunError(errText(err, 'The benchmark could not be run.'));
        } finally {
            setRunning(false);
        }
    }

    return (
        <div className="mt-10 flex flex-col gap-6">
            <form onSubmit={run} noValidate className={`${CARD} flex flex-col gap-8`} aria-label="Run a benchmark">
                <div>
                    <h2 className="text-2xl font-semibold tracking-tight text-zinc-900">Run a benchmark</h2>
                    <p className="mt-2 max-w-[60ch] text-zinc-500">
                        Measures encryption on payloads of the sizes you pick. Each size is repeated, so larger values take longer.
                    </p>
                </div>

                <fieldset className="flex flex-col gap-3 text-sm" data-invalid={errors.sizes ? 'true' : undefined}>
                    <div className="flex items-baseline justify-between">
                        <legend className="font-medium text-zinc-900">Payload sizes</legend>
                        <span className="font-mono text-xs text-zinc-500">{sizes.length} selected</span>
                    </div>
                    <div role="group" className="flex flex-wrap gap-2">
                        {options.map((s) => (
                            <Chip key={s} selected={sizes.includes(s)} onClick={() => toggle(s)}>
                                {formatBytes(s)}
                            </Chip>
                        ))}
                    </div>
                    {errors.sizes && (
                        <p role="alert" className="text-[13px] text-red-700">
                            {errors.sizes}
                        </p>
                    )}
                </fieldset>

                <div className="grid gap-6 md:grid-cols-2">
                    <div className="flex flex-col gap-2">
                        <label htmlFor="bench-custom" className="text-sm font-medium text-zinc-900">
                            Custom size <span className="font-normal text-zinc-500">(bytes)</span>
                        </label>
                        <div className="flex gap-2">
                            <input
                                id="bench-custom"
                                className={inputClass}
                                inputMode="numeric"
                                value={customInput}
                                onChange={(e) => setCustomInput(e.target.value)}
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter') {
                                        e.preventDefault();
                                        addCustom();
                                    }
                                }}
                                placeholder="e.g. 524288"
                            />
                            <button type="button" onClick={addCustom} className={`${BTN_OUTLINE} !min-h-14 shrink-0`}>
                                <Plus size={16} weight="bold" />
                                Add
                            </button>
                        </div>
                        {errors.custom && (
                            <p role="alert" className="text-[13px] text-red-700">
                                {errors.custom}
                            </p>
                        )}
                    </div>

                    <FormField label="Repeats" error={errors.repeats} hint="How many times each size is measured.">
                        <input
                            className={inputClass}
                            type="number"
                            min={1}
                            inputMode="numeric"
                            value={repeats}
                            onChange={(e) => {
                                setRepeats(e.target.value);
                                setErrors((x) => ({ ...x, repeats: '' }));
                            }}
                        />
                    </FormField>
                </div>

                {runError && <FormAlert>{runError}</FormAlert>}

                <div className="flex flex-wrap items-center gap-4">
                    <button type="submit" disabled={running} className={BTN_PRIMARY}>
                        <Play size={16} weight="fill" />
                        {running ? 'Running...' : 'Run benchmark'}
                    </button>
                    {running && (
                        <p role="status" className="text-sm text-zinc-500">
                            This can take a while for large sizes. Keep this tab open.
                        </p>
                    )}
                </div>
            </form>

            {running && (
                <div aria-hidden className="h-48 animate-pulse rounded-[2.5rem] bg-zinc-200/60" />
            )}

            {!running && result !== null && (
                <ResultCard
                    title="Latest run"
                    value={result}
                    footnote={ranAt ? `Finished at ${ranAt.toLocaleTimeString('en-GB')}` : undefined}
                />
            )}

            {summaryState === 'loading' && <div aria-hidden className="h-48 animate-pulse rounded-[2.5rem] bg-zinc-200/60" />}

            {summaryState === 'error' && (
                <div className="flex flex-col items-start gap-3">
                    <FormAlert>{summaryError}</FormAlert>
                    <button type="button" onClick={loadSummary} className={BTN_OUTLINE}>
                        <ArrowClockwise size={16} />
                        Try again
                    </button>
                </div>
            )}

            {summaryState === 'ready' && (
                <ResultCard
                    title="Summary"
                    value={summary}
                    footnote="Results of past runs."
                    action={
                        <button type="button" onClick={loadSummary} className={BTN_OUTLINE}>
                            <ArrowClockwise size={16} />
                            Refresh
                        </button>
                    }
                />
            )}
        </div>
    );
}