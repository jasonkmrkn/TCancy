'use client';

import { SECTION_LABEL } from '@/components/home/Band';
import { formatBytes } from '@/components/JsonView';

/* ------------------------------------------------------------------ */
/* Parsing                                                             */
/* ------------------------------------------------------------------ */

type Stat = { avg: number; min: number; max: number };

export type AlgoResult = {
    key: string;
    name: string;
    mode: string;
    kind: string;
    keyBits: number | null;
    runs: { crypto: number; integrity: number; total: number }[];
    total: Stat;
    crypto: Stat;
    mbps: number;
};

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);

function toStat(v: unknown): Stat | null {
    const n = num(v);
    if (n !== null) return { avg: n, min: n, max: n };
    if (isObj(v)) {
        const avg = num(v.avg);
        if (avg === null) return null;
        return { avg, min: num(v.min) ?? avg, max: num(v.max) ?? avg };
    }
    return null;
}

function toAlgo(o: Record<string, unknown>): AlgoResult | null {
    const total = toStat(o.total_ms);
    const crypto = toStat(o.crypto_ms);
    const mbps = num(o.crypto_mb_per_s) ?? num(o.mb_per_s);
    if (!total || !crypto || mbps === null) return null;
    const runs = Array.isArray(o.runs)
        ? o.runs.filter(isObj).map((r) => ({
            crypto: num(r.crypto_ms) ?? 0,
            integrity: num(r.integrity_ms) ?? 0,
            total: num(r.total_ms) ?? 0,
        }))
        : [];
    const name = typeof o.name === 'string' ? o.name : String(o.algorithm ?? '');
    return {
        key: String(o.algorithm ?? name),
        name,
        mode: typeof o.mode === 'string' ? o.mode : '',
        kind: typeof o.kind === 'string' ? o.kind : '',
        keyBits: num(o.key_bits),
        runs,
        total,
        crypto,
        mbps,
    };
}

/** Finds the list of per-algorithm results anywhere in a benchmark response, plus its other scalar fields. */
export function parseAlgorithms(data: unknown): { algos: AlgoResult[]; meta: [string, string | number | boolean][] } | null {
    const tryArray = (a: unknown): AlgoResult[] | null => {
        if (!Array.isArray(a) || a.length === 0) return null;
        const out = a.map((x) => (isObj(x) ? toAlgo(x) : null));
        return out.every(Boolean) ? (out as AlgoResult[]) : null;
    };
    const direct = tryArray(data);
    if (direct) return { algos: direct, meta: [] };
    if (!isObj(data)) return null;
    for (const [k, v] of Object.entries(data)) {
        const found = tryArray(v) ?? (isObj(v) ? tryArray(Object.values(v)) : null);
        if (found) {
            const meta = Object.entries(data).filter(
                (e): e is [string, string | number | boolean] => e[0] !== k && ['string', 'number', 'boolean'].includes(typeof e[1]),
            );
            return { algos: found, meta };
        }
    }
    return null;
}

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

const SHADES = ['#18181b', '#71717a', '#a1a1aa', '#3f3f46', '#d4d4d8'];
const DASHES = ['', '7 4', '2 3', '10 3 2 3', '4 4'];

const fmt = (n: number, d = 2) => n.toLocaleString(undefined, { maximumFractionDigits: d });
const cap = (s: string) => s.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());

function Legend({ items }: { items: { label: string; swatch: React.ReactNode }[] }) {
    return (
        <ul className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-xs text-zinc-600">
            {items.map((i) => (
                <li key={i.label} className="flex items-center gap-2">
                    {i.swatch}
                    {i.label}
                </li>
            ))}
        </ul>
    );
}

function Panel({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
    return (
        <section className="rounded-[2rem] border border-zinc-200 bg-white p-6 md:p-8">
            <h4 className={SECTION_LABEL}>{title}</h4>
            {note && <p className="mt-2 max-w-[62ch] text-sm leading-relaxed text-zinc-500">{note}</p>}
            <div className="mt-6">{children}</div>
        </section>
    );
}

/* ------------------------------------------------------------------ */
/* Charts                                                              */
/* ------------------------------------------------------------------ */

function Throughput({ algos }: { algos: AlgoResult[] }) {
    const sorted = [...algos].sort((a, b) => b.mbps - a.mbps);
    const max = sorted[0].mbps || 1;
    const slowest = sorted[sorted.length - 1].mbps || 1;
    return (
        <ul className="flex flex-col gap-4">
            {sorted.map((a, i) => (
                <li key={a.key} className="grid grid-cols-[5.5rem_1fr] items-center gap-x-4 gap-y-1 sm:grid-cols-[7rem_1fr_13rem]">
                    <span className="text-sm font-medium text-zinc-900">{a.name}</span>
                    <div className="h-3 overflow-hidden rounded-full bg-zinc-100">
                        <div
                            className="h-full rounded-full"
                            style={{ width: `${Math.max((a.mbps / max) * 100, 1.5)}%`, background: i === 0 ? '#18181b' : '#a1a1aa' }}
                        />
                    </div>
                    <span className="col-span-2 font-mono text-xs tabular-nums text-zinc-600 sm:col-span-1 sm:text-right">
                        {fmt(a.mbps, 1)} MB/s{sorted.length > 1 && i !== sorted.length - 1 ? ` · ${fmt(a.mbps / slowest, 1)}× ${sorted[sorted.length - 1].name}` : ''}
                    </span>
                </li>
            ))}
        </ul>
    );
}

function TimeRange({ algos }: { algos: AlgoResult[] }) {
    const max = Math.max(...algos.map((a) => a.total.max)) || 1;
    const pct = (v: number) => `${(v / max) * 100}%`;
    return (
        <>
            <ul className="flex flex-col gap-6">
                {algos.map((a) => (
                    <li key={a.key} className="grid grid-cols-[5.5rem_1fr] items-center gap-x-4 gap-y-2 sm:grid-cols-[7rem_1fr_9rem]">
                        <span className="text-sm font-medium text-zinc-900">{a.name}</span>
                        <div className="relative h-8">
                            {/* total avg */}
                            <div className="absolute inset-x-0 top-0 h-3 rounded-full bg-zinc-100">
                                <div className="h-full rounded-full bg-zinc-300" style={{ width: pct(a.total.avg) }} />
                            </div>
                            {/* crypto avg */}
                            <div className="absolute inset-x-0 top-5 h-3 rounded-full bg-zinc-100">
                                <div className="h-full rounded-full bg-zinc-900" style={{ width: pct(a.crypto.avg) }} />
                            </div>
                            {/* min-max whisker on total */}
                            <div className="absolute top-[0.2rem] h-1 -translate-y-px" style={{ left: pct(a.total.min), width: `calc(${pct(a.total.max)} - ${pct(a.total.min)})` }}>
                                <div className="absolute inset-y-0 left-0 right-0 top-1/2 h-px bg-zinc-500" />
                                <div className="absolute -top-1 left-0 h-3 w-px bg-zinc-500" />
                                <div className="absolute -top-1 right-0 h-3 w-px bg-zinc-500" />
                            </div>
                        </div>
                        <span className="col-span-2 font-mono text-xs tabular-nums text-zinc-600 sm:col-span-1 sm:text-right">
                            {fmt(a.total.avg)} total · {fmt(a.crypto.avg)} crypto
                        </span>
                    </li>
                ))}
            </ul>
            <Legend
                items={[
                    { label: 'Total, average', swatch: <span className="h-2.5 w-5 rounded-full bg-zinc-300" /> },
                    { label: 'Total, min to max', swatch: <span className="h-3 w-5 border-x border-zinc-500 after:block after:h-1.5 after:border-b after:border-zinc-500" /> },
                    { label: 'Crypto only, average', swatch: <span className="h-2.5 w-5 rounded-full bg-zinc-900" /> },
                ]}
            />
        </>
    );
}

function RunsChart({ algos }: { algos: AlgoResult[] }) {
    const series = algos.filter((a) => a.runs.length > 0);
    if (series.length === 0) return null;
    const W = 900;
    const H = 260;
    const P = { l: 48, r: 16, t: 12, b: 28 };
    const n = Math.max(...series.map((a) => a.runs.length));
    const max = Math.max(...series.flatMap((a) => a.runs.map((r) => r.total))) * 1.08 || 1;
    const x = (i: number) => P.l + (n === 1 ? 0 : (i / (n - 1)) * (W - P.l - P.r));
    const y = (v: number) => P.t + (1 - v / max) * (H - P.t - P.b);
    const ticks = [0, 0.5, 1].map((t) => t * max);
    return (
        <>
            <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Total time of each run, per algorithm">
                {ticks.map((t) => (
                    <g key={t}>
                        <line x1={P.l} x2={W - P.r} y1={y(t)} y2={y(t)} stroke="#e4e4e7" strokeWidth="1" />
                        <text x={P.l - 8} y={y(t) + 4} textAnchor="end" fontSize="12" fill="#71717a" fontFamily="monospace">
                            {fmt(t, 1)}
                        </text>
                    </g>
                ))}
                {Array.from({ length: n }, (_, i) => (
                    <text key={i} x={x(i)} y={H - 8} textAnchor="middle" fontSize="12" fill="#71717a" fontFamily="monospace">
                        {i + 1}
                    </text>
                ))}
                {series.map((a, si) => (
                    <g key={a.key}>
                        <polyline
                            fill="none"
                            stroke={SHADES[si % SHADES.length]}
                            strokeWidth="2.25"
                            strokeDasharray={DASHES[si % DASHES.length]}
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            points={a.runs.map((r, i) => `${x(i)},${y(r.total)}`).join(' ')}
                        />
                        {a.runs.map((r, i) => (
                            <circle key={i} cx={x(i)} cy={y(r.total)} r="3" fill="#fff" stroke={SHADES[si % SHADES.length]} strokeWidth="1.75">
                                <title>{`${a.name}, run ${i + 1}: ${fmt(r.total, 3)} ms`}</title>
                            </circle>
                        ))}
                    </g>
                ))}
                <text x={P.l} y={10} fontSize="12" fill="#71717a" fontFamily="monospace" dy="-1" />
            </svg>
            <p className="mt-1 text-center font-mono text-[11px] uppercase tracking-wider text-zinc-400">Run number · y axis in ms</p>
            <Legend
                items={series.map((a, si) => ({
                    label: a.name,
                    swatch: (
                        <svg width="28" height="8" aria-hidden>
                            <line x1="1" x2="27" y1="4" y2="4" stroke={SHADES[si % SHADES.length]} strokeWidth="2.25" strokeDasharray={DASHES[si % DASHES.length]} strokeLinecap="round" />
                        </svg>
                    ),
                }))}
            />
        </>
    );
}

function ResultTable({ algos }: { algos: AlgoResult[] }) {
    const fastest = Math.max(...algos.map((a) => a.mbps));
    const rows = [...algos].sort((a, b) => b.mbps - a.mbps);
    const th = 'px-4 py-3 font-medium';
    return (
        <div className="overflow-x-auto rounded-2xl border border-zinc-200">
            <table className="w-full min-w-max text-left text-sm">
                <thead className="bg-zinc-50 font-mono text-xs uppercase tracking-wider text-zinc-500">
                    <tr>
                        <th className={th}>Algorithm</th>
                        <th className={th}>Mode</th>
                        <th className={th}>Kind</th>
                        <th className={`${th} text-right`}>Key bits</th>
                        <th className={`${th} text-right`}>Crypto avg ms</th>
                        <th className={`${th} text-right`}>Total avg ms</th>
                        <th className={`${th} text-right`}>MB/s</th>
                        <th className={`${th} text-right`}>Speed</th>
                    </tr>
                </thead>
                <tbody className="divide-y divide-zinc-200 tabular-nums">
                    {rows.map((a) => (
                        <tr key={a.key}>
                            <td className="px-4 py-3 font-medium text-zinc-900">{a.name}</td>
                            <td className="px-4 py-3 text-zinc-600">{a.mode}</td>
                            <td className="px-4 py-3 text-zinc-600">{a.kind}</td>
                            <td className="px-4 py-3 text-right font-mono">{a.keyBits ?? '—'}</td>
                            <td className="px-4 py-3 text-right font-mono">{fmt(a.crypto.avg, 3)}</td>
                            <td className="px-4 py-3 text-right font-mono">{fmt(a.total.avg, 3)}</td>
                            <td className="px-4 py-3 text-right font-mono">{fmt(a.mbps, 1)}</td>
                            <td className="px-4 py-3 text-right font-mono text-zinc-600">
                                {a.mbps === fastest ? 'fastest' : `${fmt(fastest / a.mbps, 1)}× slower`}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

/* ------------------------------------------------------------------ */
/* Entry                                                               */
/* ------------------------------------------------------------------ */

export default function AlgorithmChart({ algos, meta = [] }: { algos: AlgoResult[]; meta?: [string, string | number | boolean][] }) {
    const byMbps = [...algos].sort((a, b) => b.mbps - a.mbps);
    const fast = byMbps[0];
    const slow = byMbps[byMbps.length - 1];
    const warm = algos.filter((a) => a.runs.length > 1 && a.runs[0].total > 1.5 * a.total.min).length;

    return (
        <div className="flex flex-col gap-5">
            {algos.length > 1 && (
                <p className="max-w-[70ch] text-lg leading-snug tracking-tight text-zinc-900">
                    <strong className="font-semibold">{fast.name}</strong> is the fastest at {fmt(fast.mbps, 1)} MB/s, about{' '}
                    {fmt(fast.mbps / (slow.mbps || 1), 1)}× the speed of <strong className="font-semibold">{slow.name}</strong> ({fmt(slow.mbps, 1)} MB/s).
                </p>
            )}
            {meta.length > 0 && (
                <p className="font-mono text-xs text-zinc-500">
                    {meta
                        .map(([k, v]) => `${cap(k)}: ${typeof v === 'number' && /size|bytes/i.test(k) ? formatBytes(v) : String(v)}`)
                        .join('  ·  ')}
                </p>
            )}

            <Panel title="Throughput" note="How much data each algorithm encrypts per second. Longer is faster.">
                <Throughput algos={algos} />
            </Panel>

            <Panel title="Time per run" note="Average time with the fastest and slowest run marked. Total includes setup and integrity work, crypto is the encryption itself.">
                <TimeRange algos={algos} />
            </Panel>

            <Panel
                title="Every run"
                note={warm > 0 ? 'The first run is usually slower because of warm-up, which is why the average sits above the minimum.' : undefined}
            >
                <RunsChart algos={algos} />
            </Panel>

            <ResultTable algos={algos} />
            <p className="text-xs leading-relaxed text-zinc-500">
                Speed is not security. DES (64-bit key) and RC4 are considered broken or obsolete, so a faster result does not make them the better choice.
            </p>
        </div>
    );
}