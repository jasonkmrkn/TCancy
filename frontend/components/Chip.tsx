// Toggle pill used for filters and multi-select fields.
export default function Chip({
    selected,
    onClick,
    children,
}: {
    selected: boolean;
    onClick: () => void;
    children: React.ReactNode;
}) {
    return (
        <button
            type="button"
            aria-pressed={selected}
            onClick={onClick}
            className={`rounded-full border px-4 py-2 text-sm transition duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] active:translate-y-[1px] active:scale-[0.98] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900 ${selected
                    ? 'border-zinc-900 bg-zinc-900 text-zinc-50'
                    : 'border-zinc-200 bg-white text-zinc-700 hover:border-zinc-400'
                }`}
        >
            {children}
        </button>
    );
}