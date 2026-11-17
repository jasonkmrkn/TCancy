/**
 * API calls and helpers for the alumni proof flow (V8).
 *
 * Alumni (pending):  upload / view / delete the proof, list requests, allow access (grant).
 * Admin:             ask an alumnus for the proof. Opening it is in lib/proofcrypto.ts.
 *
 * The access code is not a secret on its own: it only opens with the admin's private key.
 * The server does not keep it, so the page that shows it is the only place it can be copied from.
 */
import { api } from '@/lib/api';
import { formatFingerprint } from '@/lib/keys';

export const PROOF_MAX_BYTES = 5 * 1024 * 1024;
export const PROOF_EXTS = ['pdf', 'jpg', 'png'] as const;
export type ProofExt = (typeof PROOF_EXTS)[number];

export type ProofInfo = { ext: ProofExt; size: number; sha256: string; created_at: string };

export type VerificationRequestItem = {
    id: string;
    status: 'pending' | 'granted';
    admin_username: string;
    /** The key the alumnus should compare with the secretariat's announcement. */
    admin_fingerprint: string | null;
    created_at: string;
    expires_at: string;
};

export type GrantResult = {
    request_id: string;
    grant_id: string;
    access_code: string;
    admin_fingerprint: string;
};

export type ProofRequest = {
    id: string;
    alumni_id: string;
    status: string;
    created_at: string;
    expires_at: string;
};

/** Magic bytes: the server decides the real type, this only saves a round trip. */
export function sniffProofExt(head: Uint8Array): ProofExt | null {
    if (head.length >= 4 && head[0] === 0x25 && head[1] === 0x50 && head[2] === 0x44 && head[3] === 0x46) return 'pdf';
    if (head.length >= 3 && head[0] === 0xff && head[1] === 0xd8 && head[2] === 0xff) return 'jpg';
    if (head.length >= 8 && [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a].every((b, i) => head[i] === b)) return 'png';
    return null;
}

/** Why a chosen file cannot be used, or null when it looks fine. */
export async function checkProofFile(file: File): Promise<string | null> {
    if (file.size === 0) return 'The file is empty.';
    if (file.size > PROOF_MAX_BYTES) return 'The file is too large. The limit is 5 MiB.';
    const head = new Uint8Array(await file.slice(0, 16).arrayBuffer());
    return sniffProofExt(head) ? null : 'Use a PDF, JPG or PNG file.';
}

/* ------------------------------------------------------------------ */
/* Alumni                                                              */
/* ------------------------------------------------------------------ */

export const proof = {
    /** 404 PROOF_NOT_FOUND when nothing is uploaded yet. */
    get: () => api<ProofInfo>('/me/verification-proof'),
    /** Replaces an earlier proof and ends any access that was already granted. */
    upload: (file: File) => {
        const form = new FormData();
        form.append('file', file);
        return api<ProofInfo>('/me/verification-proof', { method: 'POST', body: form });
    },
    remove: () => api<void>('/me/verification-proof', { method: 'DELETE' }),
};

export const requests = {
    list: () => api<VerificationRequestItem[]>('/me/verification-requests'),
    /** Makes K, wraps it for the admin and returns the access code. The code is only returned here. */
    grant: (id: string) => api<GrantResult>(`/me/verification-requests/${encodeURIComponent(id)}/grant`, { method: 'POST' }),
};

/* ------------------------------------------------------------------ */
/* Admin                                                               */
/* ------------------------------------------------------------------ */

/** 409: NOT_PENDING, NO_PUBLIC_KEY, NO_PROOF, REQUEST_EXISTS. */
export const requestProof = (alumniId: string) =>
    api<ProofRequest>(`/admin/alumni/${encodeURIComponent(alumniId)}/proof-request`, { method: 'POST' });

/**
 * The backend does not list an admin's requests, so the id that POST returned is kept in this
 * browser to open the proof later. It is only an id: without the private key and the access
 * code it opens nothing.
 */
const storeKey = (adminId: string) => `tcancy.proof-requests.${adminId}`;

export function savedRequests(adminId: string): Record<string, string> {
    try {
        const v = JSON.parse(localStorage.getItem(storeKey(adminId)) ?? '{}');
        return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, string>) : {};
    } catch {
        return {};
    }
}

export function saveRequest(adminId: string, alumniId: string, requestId: string | null): void {
    try {
        const all = savedRequests(adminId);
        if (requestId) all[alumniId] = requestId;
        else delete all[alumniId];
        localStorage.setItem(storeKey(adminId), JSON.stringify(all));
    } catch {
        /* storage blocked: the admin can still request again after a reload */
    }
}

/* ------------------------------------------------------------------ */
/* Sending the code by email (no server involved)                      */
/* ------------------------------------------------------------------ */

/**
 * Where the access code is sent by default. The alumnus can still change the recipients in the
 * email app. The addresses come from NEXT_PUBLIC_SECRETARIAT_EMAILS (comma-separated), set when the
 * image is built (GitHub variable SECRETARIAT_EMAILS) or in frontend/.env.local for development,
 * so no address lives in this public repository. Anything that does not look like a plain address
 * is dropped, so a stray "?", "&" or "%" cannot change the rest of the mailto link. Empty when unset.
 */
const PLAIN_ADDRESS = /^[^\s@,?&#%]+@[^\s@,?&#%]+\.[^\s@,?&#%]+$/;
export const SECRETARIAT_EMAILS: readonly string[] = (process.env.NEXT_PUBLIC_SECRETARIAT_EMAILS ?? '')
    .split(',')
    .map((s) => s.trim())
    .filter((s) => PLAIN_ADDRESS.test(s));

/**
 * A mailto: link with the recipients, subject and body filled in. The page never sends anything
 * itself: it opens the alumnus's own email app, and they press send.
 */
export function buildMailto(opts: { accessCode: string; adminUsername: string; fingerprint: string }): string {
    const subject = 'TCancy alumni verification: access code';
    const body =
        'Access code: ' + opts.accessCode + '\r\n' +
        'Admin: ' + opts.adminUsername + '\r\n' +
        'Fingerprint: ' + formatFingerprint(opts.fingerprint);
    return 'mailto:' + SECRETARIAT_EMAILS.join(',') + '?subject=' + encodeURIComponent(subject) + '&body=' + encodeURIComponent(body);
}

export function formatBytes(n: number): string {
    if (n >= 1024 * 1024) return (n / (1024 * 1024)).toFixed(1).replace(/\.0$/, '') + ' MiB';
    if (n >= 1024) return (n / 1024).toFixed(0) + ' KiB';
    return n + ' B';
}
