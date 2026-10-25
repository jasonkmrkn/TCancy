export default function FormField({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium">{label}</span>
      {children}
      {error && <span className="mt-1 block text-red-700">{error}</span>}
    </label>
  );
}

export const inputClass = 'w-full rounded border px-2 py-1';
