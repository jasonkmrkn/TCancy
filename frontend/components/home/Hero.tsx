import { Buildings, ShieldCheck } from '@phosphor-icons/react/dist/ssr';
import Band from './Band';
import HeroActions from './HeroActions';

// Decorative samples only (aria-hidden). Not real vacancies.
const CARDS = [
    {
        company: 'Kavra Pay',
        title: 'Backend Engineer Intern',
        tags: ['Internship', 'Hybrid', 'Go'],
        pos: 'left-0 top-10',
        dur: '7s',
        delay: '0s',
    },
    {
        company: 'Sandikota Labs',
        title: 'Junior Security Analyst',
        tags: ['Full-time', 'On-site', 'SIEM'],
        pos: 'left-[28%] top-[13.5rem]',
        dur: '8s',
        delay: '-2s',
    },
    {
        company: 'Tanahair Mobility',
        title: 'Product Designer',
        tags: ['Contract', 'Remote'],
        pos: 'left-[5%] top-[26rem]',
        dur: '9s',
        delay: '-4s',
    },
];

function HeroCards() {
    return (
        <div aria-hidden className="relative hidden h-[36rem] w-full lg:block">
            {CARDS.map((c) => (
                <div
                    key={c.title}
                    className={`drift absolute w-[72%] max-w-[23rem] rounded-[2rem] border border-zinc-200/60 bg-white p-6 shadow-[0_20px_40px_-15px_rgba(24,24,27,0.1)] ${c.pos}`}
                    style={{ '--dur': c.dur, '--d': c.delay } as React.CSSProperties}
                >
                    <div className="flex items-center gap-3">
                        <span className="grid h-9 w-9 place-items-center rounded-full bg-zinc-100 text-zinc-600">
                            <Buildings size={18} weight="regular" />
                        </span>
                        <span className="text-sm text-zinc-500">{c.company}</span>
                    </div>
                    <p className="mt-5 text-lg font-semibold tracking-tight text-zinc-900">{c.title}</p>
                    <div className="mt-4 flex flex-wrap gap-2">
                        {c.tags.map((t) => (
                            <span key={t} className="rounded-full bg-zinc-100 px-3 py-1 text-xs font-medium text-zinc-700">
                                {t}
                            </span>
                        ))}
                    </div>
                </div>
            ))}

            <div
                className="drift absolute right-0 top-0 flex items-center gap-2.5 rounded-full border border-zinc-200 bg-white px-4 py-2 text-sm font-medium text-zinc-900 shadow-[0_12px_24px_-12px_rgba(24,24,27,0.12)]"
                style={{ '--dur': '6s', '--d': '-1s' } as React.CSSProperties}
            >
                <span className="relative flex h-2 w-2">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-zinc-900/40" />
                    <span className="relative inline-flex h-2 w-2 rounded-full bg-zinc-900" />
                </span>
                Posted by an alumnus
            </div>

            <div
                className="drift absolute left-[58%] top-[27rem] flex items-center gap-2.5 whitespace-nowrap rounded-full bg-zinc-900 px-4 py-2.5 text-sm font-medium text-zinc-50 shadow-[0_12px_24px_-12px_rgba(24,24,27,0.35)]"
                style={{ '--dur': '7.5s', '--d': '-3s' } as React.CSSProperties}
            >
                <ShieldCheck size={18} weight="regular" />
                NIK seen only by the owner
            </div>
        </div>
    );
}

export default function Hero() {
    return (
        <Band
            tone="base"
            line={false}
            decor={
                <div
                    aria-hidden
                    className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,rgba(24,24,27,0.05)_1px,transparent_1px),linear-gradient(to_bottom,rgba(24,24,27,0.05)_1px,transparent_1px)] bg-[size:60px_60px] [mask-image:radial-gradient(ellipse_at_75%_45%,black_15%,transparent_70%)]"
                />
            }
        >
            <div className="relative grid min-h-[calc(100dvh-4rem)] items-center gap-12 py-12 lg:grid-cols-[1.05fr_1fr] lg:py-16">
                <div className="relative">
                    <span className="rise inline-flex items-center gap-2 rounded-full border border-zinc-200 bg-white px-3.5 py-1.5 text-[13px] text-zinc-600">
                        <span className="h-1.5 w-1.5 rounded-full bg-zinc-900" />
                        Jobs from alumni, for the next class
                    </span>
                    <h1
                        className="rise mt-6 max-w-[14ch] text-5xl font-semibold leading-[0.98] tracking-tighter text-zinc-900 md:text-6xl"
                        style={{ '--i': 1 } as React.CSSProperties}
                    >
                        Your first job, opened by a senior.
                    </h1>
                    <p
                        className="rise mt-6 max-w-[48ch] text-lg leading-relaxed text-zinc-500"
                        style={{ '--i': 2 } as React.CSSProperties}
                    >
                        TCancy connects graduates and students with internships and jobs posted directly by HMTC ITS alumni. Your NIK and ID card
                        are visible only to the owner of a vacancy you apply to.
                    </p>
                    <div className="rise" style={{ '--i': 3 } as React.CSSProperties}>
                        <HeroActions />
                    </div>
                </div>

                <HeroCards />
            </div>
        </Band>
    );
}