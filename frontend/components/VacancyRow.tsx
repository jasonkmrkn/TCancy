import Link from 'next/link';
import { ArrowUpRight } from '@phosphor-icons/react/dist/ssr';
import { modeLabel, typeLabel } from '@/lib/labels';

export type RowJob = {
    id: string;
    title: string;
    company: string;
    type: string;
    work_mode: string;
    location: string | null;
    deadline: string | null;
    status?: string;
    skills: { id: string; name: string }[];
};

const EASE = 'ease-[cubic-bezier(0.16,1,0.3,1)]';

export default function VacancyRow({ job, extra, index = 0 }: { job: RowJob; extra?: React.ReactNode; index?: number }) {
    return (
        <li className="rise" style={{ '--i': Math.min(index, 8) } as React.CSSProperties}>
            <Link
                href={`/vacancy/${job.id}`}
                className="group grid gap-4 px-2 py-6 transition-colors duration-300 hover:bg-white/70 sm:grid-cols-[1fr_auto] sm:items-center"
            >
                <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-3">
                        <h3 className="text-lg font-semibold tracking-tight text-zinc-900">{job.title}</h3>
                        {job.status === 'closed' && (
                            <span className="rounded-full border border-zinc-300 px-2.5 py-0.5 text-[11px] font-medium uppercase tracking-wider text-zinc-500">
                                Closed
                            </span>
                        )}
                    </div>
                    <p className="mt-1 text-sm text-zinc-500">
                        {job.company} · {typeLabel(job.type)} · {modeLabel(job.work_mode)}
                        {job.location ? ` · ${job.location}` : ''}
                    </p>
                    {job.skills.length > 0 && (
                        <div className="mt-3 flex flex-wrap gap-2">
                            {job.skills.slice(0, 4).map((s) => (
                                <span key={s.id} className="rounded-full bg-zinc-100 px-3 py-1 text-xs font-medium text-zinc-700">
                                    {s.name}
                                </span>
                            ))}
                            {job.skills.length > 4 && <span className="px-1 py-1 font-mono text-xs text-zinc-500">+{job.skills.length - 4}</span>}
                        </div>
                    )}
                    {extra}
                </div>
                <div className="flex items-center gap-4 text-zinc-500">
                    {job.deadline && <span className="font-mono text-xs">Apply by {job.deadline}</span>}
                    <ArrowUpRight
                        size={20}
                        weight="regular"
                        className={`transition-transform duration-300 ${EASE} group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-zinc-900`}
                    />
                </div>
            </Link>
        </li>
    );
}