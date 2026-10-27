import { SECTION_LABEL } from '@/components/home/Band';
import { stagger } from '@/components/AuthShell';

// Small shared pieces for the account pages (profile, documents, applications).

export const EASE = 'ease-[cubic-bezier(0.16,1,0.3,1)]';

const BTN_BASE = `inline-flex min-h-11 items-center justify-center gap-2 rounded-full px-5 text-sm font-medium transition duration-300 ${EASE} active:translate-y-[1px] active:scale-[0.98] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-50`;

export const BTN_PRIMARY = `${BTN_BASE} bg-zinc-900 text-zinc-50 shadow-[inset_0_1px_0_rgba(255,255,255,0.12)] hover:bg-zinc-800 focus-visible:outline-zinc-900`;
export const BTN_OUTLINE = `${BTN_BASE} border border-zinc-200 bg-white text-zinc-900 hover:border-zinc-400 focus-visible:outline-zinc-900`;
export const BTN_DANGER = `${BTN_BASE} bg-red-700 text-white hover:bg-red-800 focus-visible:outline-red-700`;
export const BTN_DANGER_OUTLINE = `${BTN_BASE} border border-red-200 bg-white text-red-700 hover:border-red-400 focus-visible:outline-red-700`;

export const CARD =
    'rounded-[2.5rem] border border-zinc-200/60 bg-white p-8 shadow-[0_20px_40px_-15px_rgba(24,24,27,0.08)] md:p-10';

export function PageHeader({
    eyebrow,
    title,
    subtitle,
    action,
}: {
    eyebrow: string;
    title: string;
    subtitle?: string;
    action?: React.ReactNode;
}) {
    return (
        <header className="rise flex flex-wrap items-end justify-between gap-6" style={stagger(0)}>
            <div>
                <p className={SECTION_LABEL}>{eyebrow}</p>
                <h1 className="mt-3 max-w-[20ch] text-4xl font-semibold leading-[1.05] tracking-tighter text-zinc-900 md:text-5xl">
                    {title}
                </h1>
                {subtitle && <p className="mt-4 max-w-[56ch] leading-relaxed text-zinc-500">{subtitle}</p>}
            </div>
            {action}
        </header>
    );
}

export function Pill({
    children,
    tone = 'outline',
}: {
    children: React.ReactNode;
    tone?: 'solid' | 'outline' | 'muted';
}) {
    const cls =
        tone === 'solid'
            ? 'bg-zinc-900 text-zinc-50'
            : tone === 'muted'
                ? 'bg-zinc-200/70 text-zinc-600'
                : 'border border-zinc-300 text-zinc-700';
    return (
        <span className={`inline-flex rounded-full px-2.5 py-0.5 text-[11px] font-medium uppercase tracking-wider ${cls}`}>
            {children}
        </span>
    );
}

export function SignInNotice({ title, children }: { title: string; children: React.ReactNode }) {
    return (
        <div className="py-4">
            <h1 className="text-3xl font-semibold tracking-tight text-zinc-900">{title}</h1>
            <p className="mt-3 max-w-[52ch] text-zinc-500">{children}</p>
        </div>
    );
}

export function PageSkeleton() {
    return (
        <div aria-hidden className="flex animate-pulse flex-col gap-5 py-4">
            <div className="h-4 w-24 rounded-full bg-zinc-200/70" />
            <div className="h-12 w-80 max-w-full rounded-full bg-zinc-200/70" />
            <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
                <div className="h-80 rounded-[2.5rem] bg-zinc-200/60" />
                <div className="h-80 rounded-[2.5rem] bg-zinc-200/60" />
            </div>
        </div>
    );
}