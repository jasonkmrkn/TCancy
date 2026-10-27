const TONES = { base: '#fafafa', white: '#ffffff', muted: '#f4f4f5' } as const;

// Full-width background band with its own centered container. No overflow tricks.
export default function Band({
    tone = 'base',
    line = true,
    className = '',
    decor,
    children,
}: {
    tone?: keyof typeof TONES;
    line?: boolean;
    className?: string;
    decor?: React.ReactNode;
    children: React.ReactNode;
}) {
    return (
        <section
            className={`relative w-full overflow-hidden ${line ? 'border-t border-zinc-200' : ''} ${className}`}
            style={{ backgroundColor: TONES[tone] }}
        >
            {decor}
            <div className="relative mx-auto w-full max-w-7xl px-4 md:px-6">{children}</div>
        </section>
    );
}

export const SECTION_LABEL = 'text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500';