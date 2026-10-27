const TYPES: Record<string, string> = {
    internship: 'Internship',
    fulltime: 'Full-time',
    parttime: 'Part-time',
    contract: 'Contract',
};

const MODES: Record<string, string> = {
    onsite: 'On-site',
    hybrid: 'Hybrid',
    remote: 'Remote',
};

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export const typeLabel = (v: string) => TYPES[v] ?? cap(v);
export const modeLabel = (v: string) => MODES[v] ?? cap(v);

export function initials(name: string | null | undefined): string {
    if (!name) return '?';
    const parts = name.trim().split(/\s+/).slice(0, 2);
    return parts.map((p) => p.charAt(0).toUpperCase()).join('') || '?';
}