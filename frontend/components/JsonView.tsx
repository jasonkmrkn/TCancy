'use client';

import { SECTION_LABEL } from '@/components/home/Band';

/**
 * Renders an arbitrary JSON value: scalars as stat tiles, arrays of objects as tables,
 * nested objects as labelled sections. Used for backend responses that are not typed.
 */

export function formatBytes(n: number): string {
    if (n >= 1024 * 1024 && n % (1024 * 1024) === 0) return `${n / (1024 * 1024)} MB`;
    if (n >= 1024 && n % 1024 === 0) return `${n / 1024} KB`;
    return `${n.toLocaleString()} B`;
}

export const cap = (s: string) => {
    const t = s.replace(/_/g, ' ');
    return t.charAt(0).toUpperCase() + t.slice(1);
};

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

export function JsonView({ value, name = '', depth = 0 }: { value: unknown; name?: string; depth?: number }) {
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
                    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                        {scalars.map(([k, v]) => (
                            <div key={k} className="rounded-2xl bg-zinc-50 px-4 py-3">
                                <dt className="text-xs uppercase tracking-wider text-zinc-500">{cap(k)}</dt>
                                <dd className="mt-1 whitespace-nowrap font-mono text-sm font-semibold tabular-nums text-zinc-900">{formatValue(k, v)}</dd>
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