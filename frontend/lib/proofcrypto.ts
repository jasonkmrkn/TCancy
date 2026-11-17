/**
 * Browser side of the alumni proof package (V7). Mirrors backend/app/verify_crypto.py.
 *
 *   access code  = base64( RSA-OAEP-3072 SHA-256 (K) ), opened with the admin's private key
 *   package      = chunks of (chunk_size + 16) bytes, each AES-256-GCM under K:
 *                    nonce = pkg_nonce (8 B) || i (4 B BE)
 *                    AAD   = grant_id (16 B) || i (4 B BE) || last (1 B)
 *
 * K only ever exists as a non-extractable CryptoKey in page memory: it is never stored, never
 * logged and its bytes are never read. The decrypted proof is returned as bytes for the caller
 * to show; nothing here writes it anywhere.
 */
import { api, ApiError, toError } from '@/lib/api';
import { fromB64, getLocalKey, getPrivateKey, KeysError } from '@/lib/keys';

const TAG_BYTES = 16;
const RSA_BYTES = 384; // RSA-3072
const PKG_NONCE_BYTES = 8;
const MAX_CHUNKS = 2 ** 32;

export type ProofCryptoErrorCode =
    | 'BAD_ACCESS_CODE'
    | 'WRONG_KEY'
    | 'KEY_MISMATCH'
    | 'BAD_PACKAGE'
    | 'SIZE_MISMATCH'
    | 'WEBCRYPTO_UNAVAILABLE';

const MESSAGES: Record<ProofCryptoErrorCode, string> = {
    BAD_ACCESS_CODE: 'This is not a valid access code. Paste it exactly as the alumni sent it.',
    WRONG_KEY: 'The access code could not be opened with the key in this browser. It was made for a different key.',
    KEY_MISMATCH: 'This access was made for a different key than the one stored in this browser. Restore the matching backup first.',
    BAD_PACKAGE: 'The proof could not be decrypted. The package is damaged or incomplete.',
    SIZE_MISMATCH: 'The decrypted proof does not have the expected size.',
    WEBCRYPTO_UNAVAILABLE: 'This browser cannot do the cryptography needed here. Use HTTPS or localhost.',
};

export class ProofCryptoError extends Error {
    code: ProofCryptoErrorCode;
    constructor(code: ProofCryptoErrorCode) {
        super(MESSAGES[code]);
        this.name = 'ProofCryptoError';
        this.code = code;
    }
}

const buf = (u: Uint8Array) => u as unknown as BufferSource;

function subtle(): SubtleCrypto {
    if (typeof crypto === 'undefined' || !crypto.subtle) throw new ProofCryptoError('WEBCRYPTO_UNAVAILABLE');
    return crypto.subtle;
}

function hexToBytes(hex: string): Uint8Array {
    if (!/^([0-9a-f]{2})*$/i.test(hex)) throw new ProofCryptoError('BAD_PACKAGE');
    const out = new Uint8Array(hex.length / 2);
    for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
    return out;
}

/** "7c1f6a52-3b0e-..." to its 16 bytes. */
function uuidBytes(id: string): Uint8Array {
    const hex = id.replace(/-/g, '');
    if (hex.length !== 32) throw new ProofCryptoError('BAD_PACKAGE');
    return hexToBytes(hex);
}

const be32 = (n: number) => new Uint8Array([(n >>> 24) & 255, (n >>> 16) & 255, (n >>> 8) & 255, n & 255]);

/**
 * Opens the access code with the admin's private key and returns K as a NON-EXTRACTABLE
 * AES-GCM key (decrypt only). Whitespace and line breaks added by an email client are ignored.
 */
export async function unwrapAccessCode(accessCode: string, privateKey: CryptoKey): Promise<CryptoKey> {
    const cleaned = accessCode.replace(/\s+/g, '');
    if (!/^[A-Za-z0-9+/]+={0,2}$/.test(cleaned)) throw new ProofCryptoError('BAD_ACCESS_CODE');
    let wrapped: Uint8Array;
    try {
        wrapped = fromB64(cleaned);
    } catch {
        throw new ProofCryptoError('BAD_ACCESS_CODE');
    }
    if (wrapped.length !== RSA_BYTES) throw new ProofCryptoError('BAD_ACCESS_CODE');
    try {
        return await subtle().unwrapKey(
            'raw',
            buf(wrapped),
            privateKey,
            { name: 'RSA-OAEP' },
            { name: 'AES-GCM', length: 256 },
            false,
            ['decrypt'],
        );
    } catch (e) {
        if (e instanceof ProofCryptoError) throw e;
        throw new ProofCryptoError('WRONG_KEY');
    }
}

/**
 * Decrypts the whole package chunk by chunk with the same AAD as the server. Any wrong,
 * missing, reordered or cut-off chunk fails the GCM tag and the whole call throws BAD_PACKAGE.
 */
export async function decryptPackage(
    pkg: ArrayBuffer | Uint8Array,
    k: CryptoKey,
    grantId: string,
    pkgNonceHex: string,
    chunkSize: number,
): Promise<Uint8Array> {
    const s = subtle();
    const data = pkg instanceof Uint8Array ? pkg : new Uint8Array(pkg);
    const nonce = hexToBytes(pkgNonceHex);
    if (nonce.length !== PKG_NONCE_BYTES || !Number.isInteger(chunkSize) || chunkSize < 1) {
        throw new ProofCryptoError('BAD_PACKAGE');
    }
    const step = chunkSize + TAG_BYTES;
    // An empty proof is still one chunk (just a tag), so anything shorter than a tag is damaged.
    if (data.length < TAG_BYTES) throw new ProofCryptoError('BAD_PACKAGE');
    const count = Math.ceil(data.length / step);
    if (count > MAX_CHUNKS) throw new ProofCryptoError('BAD_PACKAGE');
    const grant = uuidBytes(grantId);

    const parts: Uint8Array[] = [];
    for (let i = 0; i < count; i++) {
        const start = i * step;
        const piece = data.subarray(start, Math.min(start + step, data.length));
        if (piece.length < TAG_BYTES) throw new ProofCryptoError('BAD_PACKAGE');
        const position = be32(i);
        const iv = new Uint8Array(12);
        iv.set(nonce, 0);
        iv.set(position, PKG_NONCE_BYTES);
        const aad = new Uint8Array(21);
        aad.set(grant, 0);
        aad.set(position, 16);
        aad[20] = i === count - 1 ? 1 : 0;
        try {
            const plain = await s.decrypt({ name: 'AES-GCM', iv: buf(iv), additionalData: buf(aad), tagLength: 128 }, k, buf(piece));
            parts.push(new Uint8Array(plain));
        } catch {
            throw new ProofCryptoError('BAD_PACKAGE');
        }
    }
    const total = parts.reduce((n, p) => n + p.length, 0);
    const out = new Uint8Array(total);
    let at = 0;
    for (const p of parts) {
        out.set(p, at);
        at += p.length;
    }
    return out;
}

/* ------------------------------------------------------------------ */
/* Opening a grant (admin)                                             */
/* ------------------------------------------------------------------ */

/** GET /admin/proof-grants/{request_id}. */
export type GrantMetadata = {
    request_id: string;
    grant_id: string;
    ext: 'pdf' | 'jpg' | 'png';
    size: number;
    pkg_size: number;
    pkg_nonce: string;
    chunk_size: number;
    recipient_fingerprint: string;
    expires_at: string;
    opened_at: string | null;
};

export const PROOF_MIME: Record<GrantMetadata['ext'], string> = {
    pdf: 'application/pdf',
    jpg: 'image/jpeg',
    png: 'image/png',
};

export const getGrantMetadata = (requestId: string) =>
    api<GrantMetadata>(`/admin/proof-grants/${encodeURIComponent(requestId)}`);

/** GET /admin/proof-grants/{request_id}/package: the encrypted bytes. The first call sets opened_at. */
export async function fetchPackage(requestId: string): Promise<Uint8Array> {
    let res: Response;
    try {
        res = await fetch(`/api/v1/admin/proof-grants/${encodeURIComponent(requestId)}/package`, { credentials: 'include' });
    } catch {
        throw new ApiError(0, 'NETWORK', 'Cannot reach the server. Check your connection.');
    }
    if (!res.ok) throw await toError(res);
    return new Uint8Array(await res.arrayBuffer());
}

export type OpenedProof = { bytes: Uint8Array; ext: GrantMetadata['ext']; mime: string; meta: GrantMetadata };

/**
 * The whole admin flow for one request: check the key in this browser is the one the access
 * was made for, open K, download the package, decrypt it. Throws KeysError (no local key),
 * ProofCryptoError, or ApiError (for example 410 GRANT_ENDED).
 */
export async function openProof(userId: string, requestId: string, accessCode: string): Promise<OpenedProof> {
    const meta = await getGrantMetadata(requestId);
    const local = await getLocalKey(userId);
    if (!local) throw new KeysError('NO_KEY');
    if (local.fingerprint !== meta.recipient_fingerprint) throw new ProofCryptoError('KEY_MISMATCH');

    const k = await unwrapAccessCode(accessCode, await getPrivateKey(userId));
    const pkg = await fetchPackage(requestId);
    if (pkg.length !== meta.pkg_size) throw new ProofCryptoError('BAD_PACKAGE');
    const bytes = await decryptPackage(pkg, k, meta.grant_id, meta.pkg_nonce, meta.chunk_size);
    if (bytes.length !== meta.size) throw new ProofCryptoError('SIZE_MISMATCH');
    return { bytes, ext: meta.ext, mime: PROOF_MIME[meta.ext], meta };
}
