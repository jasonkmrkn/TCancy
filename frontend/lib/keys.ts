/**
 * Admin key pair for the proof-of-alumni flow (V3).
 *
 * - RSA-OAEP 3072, SHA-256, generated with WebCrypto in the admin's browser.
 * - The private key is stored in IndexedDB as a NON-EXTRACTABLE CryptoKey. The only time
 *   its bytes exist is while a new key is generated: they are encrypted into the
 *   .tcancykey backup, then the key is re-imported as non-extractable and the bytes are zeroed.
 * - Backup format (.tcancykey), see the A2 master context, section 3:
 *     { v:1, fingerprint, kdf:"PBKDF2-SHA256", iter:600000, salt:b64(16), iv:b64(12), ct:b64 }
 *   ct = AES-256-GCM(PKCS#8). Passphrase: at least 12 characters.
 * - Fingerprint = SHA-256 (hex) of the SPKI DER.
 * - Only the public key goes to the server: POST /admin/keys { spki }. The server computes the
 *   fingerprint and expires_at itself; a new key revokes the old one.
 *   GET /admin/keys returns the one active key, or 404 KEY_NOT_FOUND.
 *
 * Set NEXT_PUBLIC_KEYS_DUMMY=1 to use an in-memory fake of /admin/keys.
 */
import { api, ApiError } from '@/lib/api';

/* ------------------------------------------------------------------ */
/* Constants and types                                                 */
/* ------------------------------------------------------------------ */

export const PBKDF2_ITERATIONS = 600_000;
export const PASSPHRASE_MIN = 12;
export const KEY_LIFETIME_DAYS = 365;

const RSA_PARAMS: RsaHashedKeyGenParams = {
    name: 'RSA-OAEP',
    modulusLength: 3072,
    publicExponent: new Uint8Array([0x01, 0x00, 0x01]),
    hash: 'SHA-256',
};
const IMPORT_PARAMS: RsaHashedImportParams = { name: 'RSA-OAEP', hash: 'SHA-256' };
const PRIVATE_USAGES: KeyUsage[] = ['decrypt', 'unwrapKey'];

export type BackupFile = {
    v: 1;
    fingerprint: string;
    kdf: 'PBKDF2-SHA256';
    iter: number;
    salt: string;
    iv: string;
    ct: string;
};

/** What the UI may show about the key kept in this browser. Never includes the private key. */
export type LocalKeyInfo = {
    fingerprint: string;
    spki: string;
    createdAt: string;
    /** null when it is not known yet (a freshly imported backup that the server has not confirmed). */
    expiresAt: string | null;
};

/** The admin's active key as the server returns it (GET and POST /admin/keys). */
export type ServerKey = {
    id: string;
    algorithm?: string;
    fingerprint: string;
    created_at: string;
    expires_at: string;
};

export type KeysErrorCode =
    | 'WEBCRYPTO_UNAVAILABLE'
    | 'PASSPHRASE_TOO_SHORT'
    | 'BAD_BACKUP'
    | 'WRONG_PASSPHRASE'
    | 'FINGERPRINT_MISMATCH'
    | 'SERVER_KEY_MISMATCH'
    | 'STORE_FAILED'
    | 'NO_KEY';

const KEYS_MESSAGES: Record<KeysErrorCode, string> = {
    WEBCRYPTO_UNAVAILABLE: 'This browser cannot do the cryptography needed here. Use HTTPS or localhost in an up-to-date browser.',
    PASSPHRASE_TOO_SHORT: `The passphrase must have at least ${PASSPHRASE_MIN} characters.`,
    BAD_BACKUP: 'This is not a valid .tcancykey file.',
    WRONG_PASSPHRASE: 'The passphrase is wrong, or the file was changed.',
    FINGERPRINT_MISMATCH: 'The key inside this backup does not match the fingerprint written in the file.',
    SERVER_KEY_MISMATCH: 'The server registered a different fingerprint than this browser computed. The key was not saved.',
    STORE_FAILED: 'The key was created but could not be saved in this browser. Keep the backup file and import it.',
    NO_KEY: 'There is no admin key in this browser. Create one or import a backup.',
};

export class KeysError extends Error {
    code: KeysErrorCode;
    /** Set when the key already exists on the server but could not be stored locally. */
    backup?: BackupFile;
    constructor(code: KeysErrorCode, backup?: BackupFile) {
        super(KEYS_MESSAGES[code]);
        this.name = 'KeysError';
        this.code = code;
        this.backup = backup;
    }
}

/* ------------------------------------------------------------------ */
/* Byte helpers                                                        */
/* ------------------------------------------------------------------ */

// TS lib typings differ between versions on what counts as a BufferSource.
const buf = (u: Uint8Array) => u as unknown as BufferSource;

export function toB64(bytes: ArrayBuffer | Uint8Array): string {
    const u = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
    let s = '';
    for (let i = 0; i < u.length; i++) s += String.fromCharCode(u[i]);
    return btoa(s);
}

export function fromB64(b64: string): Uint8Array {
    const s = atob(b64);
    const u = new Uint8Array(s.length);
    for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i);
    return u;
}

const toHex = (b: ArrayBuffer) =>
    Array.from(new Uint8Array(b), (x) => x.toString(16).padStart(2, '0')).join('');

function subtle(): SubtleCrypto {
    if (typeof crypto === 'undefined' || !crypto.subtle) throw new KeysError('WEBCRYPTO_UNAVAILABLE');
    return crypto.subtle;
}

/** SHA-256 hex of the SPKI DER. */
export async function fingerprintOf(spki: ArrayBuffer | Uint8Array): Promise<string> {
    const u = spki instanceof Uint8Array ? spki : new Uint8Array(spki);
    return toHex(await subtle().digest('SHA-256', buf(u)));
}

/** "AB:CD:..." for showing and for comparing with the secretariat's announcement. */
export function formatFingerprint(hex: string): string {
    return (hex.toUpperCase().match(/.{1,2}/g) ?? []).join(':');
}

/* ------------------------------------------------------------------ */
/* Backup (.tcancykey)                                                 */
/* ------------------------------------------------------------------ */

function checkPassphrase(p: string): string {
    if ([...p].length < PASSPHRASE_MIN) throw new KeysError('PASSPHRASE_TOO_SHORT');
    // Same normalisation on both sides, so the same typed passphrase works on any keyboard layout.
    return p.normalize('NFKC');
}

async function backupKey(passphrase: string, salt: Uint8Array, iter: number, usage: KeyUsage): Promise<CryptoKey> {
    const s = subtle();
    const base = await s.importKey('raw', buf(new TextEncoder().encode(passphrase)), 'PBKDF2', false, ['deriveKey']);
    return s.deriveKey(
        { name: 'PBKDF2', hash: 'SHA-256', salt: buf(salt), iterations: iter },
        base,
        { name: 'AES-GCM', length: 256 },
        false,
        [usage],
    );
}

async function encryptBackup(pkcs8: Uint8Array, fingerprint: string, passphrase: string): Promise<BackupFile> {
    const salt = crypto.getRandomValues(new Uint8Array(16));
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const key = await backupKey(passphrase, salt, PBKDF2_ITERATIONS, 'encrypt');
    const ct = await subtle().encrypt({ name: 'AES-GCM', iv: buf(iv) }, key, buf(pkcs8));
    return {
        v: 1,
        fingerprint,
        kdf: 'PBKDF2-SHA256',
        iter: PBKDF2_ITERATIONS,
        salt: toB64(salt),
        iv: toB64(iv),
        ct: toB64(ct),
    };
}

function parseBackup(raw: string | unknown): BackupFile {
    let o: unknown = raw;
    if (typeof raw === 'string') {
        try {
            o = JSON.parse(raw);
        } catch {
            throw new KeysError('BAD_BACKUP');
        }
    }
    if (typeof o !== 'object' || o === null) throw new KeysError('BAD_BACKUP');
    const b = o as Record<string, unknown>;
    const isStr = (v: unknown): v is string => typeof v === 'string' && v.length > 0;
    if (
        b.v !== 1 ||
        b.kdf !== 'PBKDF2-SHA256' ||
        // A fixed value: a file must not be able to pick a weaker (or absurdly slow) setting.
        b.iter !== PBKDF2_ITERATIONS ||
        !isStr(b.fingerprint) ||
        !/^[0-9a-f]{64}$/.test(b.fingerprint) ||
        !isStr(b.salt) ||
        !isStr(b.iv) ||
        !isStr(b.ct)
    ) {
        throw new KeysError('BAD_BACKUP');
    }
    try {
        if (fromB64(b.salt).length !== 16 || fromB64(b.iv).length !== 12) throw new Error();
        fromB64(b.ct);
    } catch {
        throw new KeysError('BAD_BACKUP');
    }
    return b as unknown as BackupFile;
}

async function decryptBackup(file: BackupFile, passphrase: string): Promise<Uint8Array> {
    const key = await backupKey(passphrase, fromB64(file.salt), file.iter, 'decrypt');
    try {
        const pt = await subtle().decrypt({ name: 'AES-GCM', iv: buf(fromB64(file.iv)) }, key, buf(fromB64(file.ct)));
        return new Uint8Array(pt);
    } catch {
        throw new KeysError('WRONG_PASSPHRASE');
    }
}

/** Saves the backup as <name>.tcancykey through the browser's download. */
export function downloadBackup(backup: BackupFile): void {
    const blob = new Blob([JSON.stringify(backup, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `tcancy-admin-${backup.fingerprint.slice(0, 8)}.tcancykey`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/* ------------------------------------------------------------------ */
/* IndexedDB                                                           */
/* ------------------------------------------------------------------ */

const DB_NAME = 'tcancy-keys';
const STORE = 'keys';

type StoredKey = LocalKeyInfo & { id: string; privateKey: CryptoKey };

function openDb(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
        if (typeof indexedDB === 'undefined') return reject(new Error('no indexedDB'));
        const req = indexedDB.open(DB_NAME, 1);
        req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: 'id' });
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
    });
}

async function withStore<T>(mode: IDBTransactionMode, run: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
    const db = await openDb();
    try {
        return await new Promise<T>((resolve, reject) => {
            const tx = db.transaction(STORE, mode);
            const req = run(tx.objectStore(STORE));
            tx.oncomplete = () => resolve(req.result);
            tx.onerror = () => reject(tx.error);
            tx.onabort = () => reject(tx.error);
        });
    } finally {
        db.close();
    }
}

const readStored = (userId: string) => withStore<StoredKey | undefined>('readonly', (s) => s.get(userId));
const writeStored = (rec: StoredKey) => withStore('readwrite', (s) => s.put(rec));

const publicInfo = (r: StoredKey): LocalKeyInfo => ({
    fingerprint: r.fingerprint,
    spki: r.spki,
    createdAt: r.createdAt,
    expiresAt: r.expiresAt,
});

/** The key kept in this browser for this account, or null. */
export async function getLocalKey(userId: string): Promise<LocalKeyInfo | null> {
    try {
        const r = await readStored(userId);
        return r ? publicInfo(r) : null;
    } catch {
        return null;
    }
}

/** For proofcrypto (V7): the non-extractable private key, usable for decrypt and unwrapKey only. */
export async function getPrivateKey(userId: string): Promise<CryptoKey> {
    let r: StoredKey | undefined;
    try {
        r = await readStored(userId);
    } catch {
        throw new KeysError('NO_KEY');
    }
    if (!r) throw new KeysError('NO_KEY');
    return r.privateKey;
}

/** Removes the key from this browser (for example on a shared computer). The server is not told. */
export async function deleteLocalKey(userId: string): Promise<void> {
    await withStore('readwrite', (s) => s.delete(userId));
}

/* ------------------------------------------------------------------ */
/* Server: /admin/keys                                                 */
/* ------------------------------------------------------------------ */

const DUMMY = process.env.NEXT_PUBLIC_KEYS_DUMMY === '1';
let dummyKey: ServerKey | null = null;

/** POST /admin/keys { spki }. The server revokes the previous key and closes grants made to it. */
export async function registerPublicKey(spki: string): Promise<ServerKey> {
    if (DUMMY) {
        const now = new Date();
        dummyKey = {
            id: crypto.randomUUID(),
            fingerprint: await fingerprintOf(fromB64(spki)),
            created_at: now.toISOString(),
            expires_at: new Date(now.getTime() + KEY_LIFETIME_DAYS * 86_400_000).toISOString(),
        };
        return dummyKey;
    }
    return api<ServerKey>('/admin/keys', { method: 'POST', body: { spki } });
}

/** GET /admin/keys: the active key, or null when there is none (404 KEY_NOT_FOUND). */
export async function getServerKey(): Promise<ServerKey | null> {
    if (DUMMY) return dummyKey && Date.parse(dummyKey.expires_at) > Date.now() ? dummyKey : null;
    try {
        return await api<ServerKey>('/admin/keys');
    } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
    }
}

/* ------------------------------------------------------------------ */
/* Create                                                              */
/* ------------------------------------------------------------------ */

export type KeyMaterial = {
    spki: string;
    fingerprint: string;
    backup: BackupFile;
    privateKey: CryptoKey;
};

/**
 * Generates a key pair and its encrypted backup. Nothing is stored or sent yet.
 * The returned private key is non-extractable.
 */
export async function generateKeyMaterial(passphrase: string): Promise<KeyMaterial> {
    const pass = checkPassphrase(passphrase);
    const s = subtle();

    const pair = (await s.generateKey(RSA_PARAMS, true, ['encrypt', 'decrypt', 'wrapKey', 'unwrapKey'])) as CryptoKeyPair;
    const spki = new Uint8Array(await s.exportKey('spki', pair.publicKey));
    const pkcs8 = new Uint8Array(await s.exportKey('pkcs8', pair.privateKey));
    try {
        const fingerprint = await fingerprintOf(spki);
        const backup = await encryptBackup(pkcs8, fingerprint, pass);
        // The same key again, this time one that can never be exported.
        const privateKey = await s.importKey('pkcs8', buf(pkcs8), IMPORT_PARAMS, false, PRIVATE_USAGES);
        return {
            spki: toB64(spki),
            fingerprint,
            backup,
            privateKey,
        };
    } finally {
        pkcs8.fill(0); // best effort
    }
}

async function saveKey(userId: string, m: { spki: string; fingerprint: string; expiresAt: string | null; privateKey: CryptoKey }) {
    await writeStored({
        id: userId,
        privateKey: m.privateKey,
        spki: m.spki,
        fingerprint: m.fingerprint,
        createdAt: new Date().toISOString(),
        expiresAt: m.expiresAt,
    });
}

/**
 * Creates a new admin key: generate, register the public key (which revokes the old one),
 * then keep the private key in this browser. The caller must hand `backup` to the admin
 * (downloadBackup) right away. It is the only copy that can restore the key.
 *
 * Order matters: if the server refuses, nothing is stored and any existing local key stays.
 */
export async function createAdminKey(
    userId: string,
    passphrase: string,
): Promise<{ key: LocalKeyInfo; backup: BackupFile; server: ServerKey }> {
    const m = await generateKeyMaterial(passphrase);
    const server = await registerPublicKey(m.spki);
    // The server derives its own fingerprint from the SPKI; it must agree with ours.
    if (server.fingerprint !== m.fingerprint) throw new KeysError('SERVER_KEY_MISMATCH', m.backup);
    const expiresAt = server.expires_at;
    try {
        await saveKey(userId, { ...m, expiresAt });
    } catch {
        throw new KeysError('STORE_FAILED', m.backup);
    }
    return {
        key: { fingerprint: m.fingerprint, spki: m.spki, createdAt: new Date().toISOString(), expiresAt },
        backup: m.backup,
        server,
    };
}

/* ------------------------------------------------------------------ */
/* Import                                                              */
/* ------------------------------------------------------------------ */

/** The SPKI of a PKCS#8 RSA private key. WebCrypto cannot export it directly, so go through the JWK. */
async function spkiFromPkcs8(pkcs8: Uint8Array): Promise<Uint8Array> {
    const s = subtle();
    let jwk: JsonWebKey;
    try {
        const temp = await s.importKey('pkcs8', buf(pkcs8), IMPORT_PARAMS, true, ['decrypt']);
        jwk = await s.exportKey('jwk', temp);
    } catch {
        throw new KeysError('BAD_BACKUP');
    }
    if (!jwk.n || !jwk.e) throw new KeysError('BAD_BACKUP');
    const pub = await s.importKey(
        'jwk',
        { kty: 'RSA', n: jwk.n, e: jwk.e, alg: 'RSA-OAEP-256', ext: true },
        IMPORT_PARAMS,
        true,
        ['encrypt'],
    );
    return new Uint8Array(await s.exportKey('spki', pub));
}

async function readSource(source: string | Blob): Promise<string> {
    return typeof source === 'string' ? source : source.text();
}

/**
 * Restores the key from a .tcancykey file. The fingerprint that comes out must equal the one
 * written in the file, otherwise nothing is stored. `matchesServer` says whether the restored
 * key is the one the server currently treats as active (null when the server could not be asked).
 */
export async function importBackup(
    userId: string,
    source: string | Blob,
    passphrase: string,
): Promise<{ key: LocalKeyInfo; matchesServer: boolean | null }> {
    const pass = checkPassphrase(passphrase);
    const file = parseBackup(await readSource(source));
    const pkcs8 = await decryptBackup(file, pass);
    try {
        const spki = await spkiFromPkcs8(pkcs8);
        if ((await fingerprintOf(spki)) !== file.fingerprint) throw new KeysError('FINGERPRINT_MISMATCH');
        const privateKey = await subtle().importKey('pkcs8', buf(pkcs8), IMPORT_PARAMS, false, PRIVATE_USAGES);

        let matchesServer: boolean | null = null;
        let expiresAt: string | null = null;
        try {
            const active = await getServerKey();
            matchesServer = !!active && active.fingerprint === file.fingerprint;
            if (matchesServer) expiresAt = active?.expires_at ?? null;
        } catch {
            /* offline or not an admin session: the key is still restored */
        }

        const rec = { spki: toB64(spki), fingerprint: file.fingerprint, expiresAt, privateKey };
        try {
            await saveKey(userId, rec);
        } catch {
            throw new KeysError('STORE_FAILED');
        }
        return {
            key: { fingerprint: file.fingerprint, spki: rec.spki, createdAt: new Date().toISOString(), expiresAt },
            matchesServer,
        };
    } finally {
        pkcs8.fill(0); // best effort
    }
}