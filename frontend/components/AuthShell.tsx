import { ArrowUUpLeft, IdentificationCard, SealCheck } from '@phosphor-icons/react/dist/ssr';
import Skyline from './Skyline';

// Usage: <div className="rise" style={stagger(2)}>
export const stagger = (i: number) => ({ '--i': i }) as React.CSSProperties;

// Every line below is something the backend actually does (alumni approval, owner-only NIK/KTP view, withdraw until final).
const POINTS = [
    { Icon: SealCheck, text: 'Every vacancy is posted by an HMTC ITS alumnus approved by an admin.' },
    { Icon: IdentificationCard, text: 'Your NIK and ID card are visible only to the owner of a vacancy you apply to.' },
    { Icon: ArrowUUpLeft, text: 'Withdraw an application any time before a final decision.' },
];

function Aside() {
    return (
        <aside
            aria-hidden
            className="relative hidden h-[calc(100dvh-8rem)] min-h-[34rem] flex-col overflow-hidden rounded-[2.5rem] border border-white/10 bg-zinc-950 p-10 text-zinc-50 shadow-[inset_0_1px_0_rgba(255,255,255,0.1)] lg:sticky lg:top-24 lg:flex"
        >
            {/* grid texture, fades toward the bottom */}
            <div
                className="absolute inset-0 bg-[linear-gradient(to_right,rgba(255,255,255,0.04)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.04)_1px,transparent_1px)] bg-[size:56px_56px] [mask-image:linear-gradient(to_bottom,black_30%,transparent_85%)]"
            />
            <div className="absolute inset-x-0 top-0 h-64 bg-[radial-gradient(ellipse_at_top_left,rgba(255,255,255,0.08),transparent_70%)]" />

            <div className="relative flex items-baseline gap-0.5 text-xl font-semibold tracking-tighter">
                TCancy
                <span className="h-1.5 w-1.5 rounded-[2px] bg-emerald-500" />
            </div>

            <h2 className="relative mt-8 max-w-[17ch] text-4xl font-semibold leading-[1.05] tracking-tighter">
                Vacancies posted by the alumni who came before you.
            </h2>

            <ul className="relative mt-10 flex max-w-md flex-col gap-5">
                {POINTS.map(({ Icon, text }) => (
                    <li key={text} className="flex items-start gap-4 text-[15px] leading-relaxed text-zinc-400">
                        <Icon size={22} weight="regular" className="mt-0.5 shrink-0 text-zinc-300" />
                        {text}
                    </li>
                ))}
            </ul>

            <Skyline />
        </aside>
    );
}

export default function AuthShell({ children }: { children: React.ReactNode }) {
    return (
        <div className="grid items-start gap-12 lg:grid-cols-2 lg:gap-20">
            <div className="w-full max-w-[44rem] pb-8">{children}</div>
            <Aside />
        </div>
    );
}