export type ApiFieldError = { loc: (string | number)[]; msg: string; type?: string };

export class ApiError extends Error {
  status: number;
  code: string;
  fields: Record<string, string>;

  constructor(status: number, code: string, message: string, fields: Record<string, string> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.fields = fields;
  }
}

const BASE = '/api/v1';

const MESSAGES: Record<string, string> = {
  'not logged in': 'Please sign in first.',
  forbidden: 'You are not allowed to do that.',
  'invalid username or password': 'Invalid username or password.',
  'database unavailable': 'The service is temporarily unavailable.',
  ACCOUNT_SUSPENDED: 'This account has been suspended.',
  ACCOUNT_PENDING: 'This account is still waiting for approval.',
  USERNAME_TAKEN: 'That username is already taken.',
  EMAIL_TAKEN: 'That email is already in use.',
  NIK_TAKEN: 'That national ID number is already in use.',
  INVALID_PASSWORD: 'The password is incorrect.',
  INVALID_CURSOR: 'Invalid page cursor.',
  EMPTY_FILE: 'The file is empty.',
  DOCUMENT_LIMIT: 'You have reached the document limit.',
  FILE_TOO_LARGE: 'The file is too large.',
  UNSUPPORTED_FILE_TYPE: 'This file type is not supported.',
  STORAGE_ERROR: 'The file could not be stored. Try again later.',
  DOCUMENT_NOT_FOUND: 'Document not found.',
  DOCUMENT_IN_USE: 'This document is used by an active application.',
  JOB_NOT_FOUND: 'Vacancy not found.',
  JOB_CLOSED: 'This vacancy is closed.',
  JOB_EXPIRED: 'The deadline for this vacancy has passed.',
  INVALID_STATUS: 'This application can no longer be withdrawn.',
  ALREADY_APPLIED: 'You have already applied to this job.',
  APPLICATION_NOT_FOUND: 'Application not found.',
  APPLICATION_NOT_ACCEPTED: 'Only accepted applications can get a testimonial.',
  TESTIMONIAL_EXISTS: 'You already wrote a testimonial for this application.',
  TESTIMONIAL_NOT_FOUND: 'Testimonial not found.',
  USER_NOT_FOUND: 'User not found.',
  ALUMNI_NOT_FOUND: 'Alumni not found.',
  CANNOT_MODIFY_ADMIN: 'Admin accounts cannot be modified.',
  PROFILE_INCOMPLETE: 'The profile is incomplete.',
  ALREADY_APPROVED: 'Already approved.',
  NOT_PENDING: 'This account is not waiting for a decision.',
  NOT_JOB_OWNER: 'You can only manage your own vacancies.',
  INVALID_TRANSITION: 'That status change is not allowed.',
  NO_KTP: 'The applicant has not uploaded an ID card.',
  NO_CHANGE: 'Nothing to change.',
};

export function messageFor(code: string, fallback: string): string {
  return MESSAGES[code] ?? fallback;
}

function fieldsFrom(detail: ApiFieldError[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const item of detail) {
    const path = (item.loc ?? []).filter((p) => p !== 'body' && p !== 'query');
    const key = path.join('.') || '_';
    if (!(key in out)) out[key] = item.msg;
  }
  return out;
}

async function toError(res: Response): Promise<ApiError> {
  let detail: unknown = null;
  try {
    detail = (await res.json())?.detail;
  } catch {
    detail = null;
  }
  if (Array.isArray(detail)) {
    return new ApiError(res.status, 'VALIDATION_ERROR', 'Please check the highlighted fields.', fieldsFrom(detail));
  }
  if (typeof detail === 'string') {
    return new ApiError(res.status, detail, messageFor(detail, detail));
  }
  return new ApiError(res.status, 'UNKNOWN', `Request failed (${res.status}).`);
}

export type RequestOptions = {
  method?: string;
  body?: unknown;
  query?: Record<string, string | number | boolean | null | undefined | string[]>;
  signal?: AbortSignal;
};

export function buildUrl(path: string, query?: RequestOptions['query']): string {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query ?? {})) {
    if (Array.isArray(v)) {
      for (const item of v) params.append(k, item);
    } else if (v !== undefined && v !== null && v !== '') {
      params.set(k, String(v));
    }
  }
  const qs = params.toString();
  return `${BASE}${path}${qs ? `?${qs}` : ''}`;
}

/**
 * CSRF (double-submit cookie). The backend sets a readable cookie and expects the same
 * value back in a header on every state-changing request. The cookie is found by name
 * pattern, so it works whatever the backend calls it (csrf_token, csrftoken, ...).
 * If the cookie is HttpOnly, JavaScript cannot read it: the backend then has to expose
 * the token in a response body or a non-HttpOnly cookie.
 */
const CSRF_COOKIE = /csrf/i;
const CSRF_HEADERS = ['X-CSRF-Token', 'X-CSRFToken']; // set CSRF_HEADERS to the one name your backend checks

function readCsrfToken(): string | null {
  if (typeof document === 'undefined') return null;
  for (const part of document.cookie.split(';')) {
    const eq = part.indexOf('=');
    if (eq === -1) continue;
    if (CSRF_COOKIE.test(part.slice(0, eq).trim())) {
      return decodeURIComponent(part.slice(eq + 1).trim());
    }
  }
  return null;
}

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);

export async function api<T = unknown>(path: string, opts: RequestOptions = {}): Promise<T> {
  const method = (opts.method ?? 'GET').toUpperCase();
  const init: RequestInit = {
    method,
    credentials: 'include',
    signal: opts.signal,
  };
  const headers: Record<string, string> = {};
  if (!SAFE_METHODS.has(method)) {
    const token = readCsrfToken();
    if (token) for (const name of CSRF_HEADERS) headers[name] = token;
  }
  if (opts.body instanceof FormData) {
    init.body = opts.body;
  } else if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(opts.body);
  }
  if (Object.keys(headers).length > 0) init.headers = headers;
  let res: Response;
  try {
    res = await fetch(buildUrl(path, opts.query), init);
  } catch {
    throw new ApiError(0, 'NETWORK', 'Cannot reach the server. Check your connection.');
  }
  if (!res.ok) throw await toError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
