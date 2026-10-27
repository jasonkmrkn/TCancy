import { ApiError } from '@/lib/api';
import { documents } from '@/lib/endpoints';

export type Cipher =
    | { kind: 'json'; value: unknown }
    | { kind: 'binary'; size: number; hex: string; truncated: boolean }
    | { kind: 'text'; value: string };

export const PREVIEW_BYTES = 256;

/** The ciphertext may come back as JSON, text or raw bytes, so read it by content type. */
export async function fetchCiphertext(id: string): Promise<Cipher> {
    let res: Response;
    try {
        res = await fetch(documents.ciphertextUrl(id), { credentials: 'include' });
    } catch {
        throw new ApiError(0, 'NETWORK', 'Cannot reach the server. Check your connection.');
    }
    if (!res.ok) {
        let code = 'UNKNOWN';
        try {
            const d = (await res.json())?.detail;
            if (typeof d === 'string') code = d;
        } catch {
            /* not JSON */
        }
        throw new ApiError(res.status, code, `Request failed (${res.status}).`);
    }
    const type = res.headers.get('content-type') ?? '';
    if (type.includes('json')) return { kind: 'json', value: await res.json() };
    if (type.startsWith('text/')) return { kind: 'text', value: await res.text() };
    const bytes = new Uint8Array(await res.arrayBuffer());
    const head = bytes.slice(0, PREVIEW_BYTES);
    const hex = Array.from(head, (b) => b.toString(16).padStart(2, '0')).join(' ');
    return { kind: 'binary', size: bytes.length, hex, truncated: bytes.length > PREVIEW_BYTES };
}