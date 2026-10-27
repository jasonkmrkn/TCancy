import { WarningCircle } from '@phosphor-icons/react/dist/ssr';

// Shared field styling. `group-data-[invalid=true]` lets FormField tint the border when it has an error.
const fieldBase =
  'w-full border border-zinc-200 bg-white px-6 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 ' +
  'shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] transition duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] ' +
  'hover:border-zinc-300 focus:border-zinc-900 focus:outline-none focus:ring-4 focus:ring-zinc-900/10 ' +
  'group-data-[invalid=true]:border-red-400 group-data-[invalid=true]:focus:ring-red-500/10';

// Single-line inputs: full pill (radius 50px), taller than before.
export const inputClass = `${fieldBase}  rounded-[50px]`;

// Multi-line fields keep a softer radius so text is not clipped at the corners.
export const textareaClass = `${fieldBase} rounded-[1.75rem]`;

export const primaryButtonClass =
  'flex min-h-12 w-full items-center justify-center rounded-full bg-zinc-900 px-6 text-sm font-medium text-zinc-50 ' +
  'shadow-[inset_0_1px_0_rgba(255,255,255,0.12)] transition duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] ' +
  'hover:bg-zinc-800 active:translate-y-[1px] active:scale-[0.98] ' +
  'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900 ' +
  'disabled:cursor-not-allowed disabled:opacity-60';

export default function FormField({
  label,
  error,
  hint,
  children,
}: {
  label: string;
  error?: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="group flex flex-col gap-2 text-sm" data-invalid={error ? 'true' : undefined}>
      <span className="font-medium text-zinc-900">{label}</span>
      {children}
      {error ? (
        <span role="alert" className="text-[13px] text-red-700">
          {error}
        </span>
      ) : hint ? (
        <span className="text-[13px] text-zinc-500">{hint}</span>
      ) : null}
    </label>
  );
}

export function FormAlert({ children }: { children: React.ReactNode }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
    >
      <WarningCircle size={18} weight="regular" className="mt-0.5 shrink-0" />
      <p>{children}</p>
    </div>
  );
}