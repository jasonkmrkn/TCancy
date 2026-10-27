import { api } from './api';

// Typed wrappers for every backend route (backend/app/routers/*, schemas in backend/app/schemas.py).
// Paths are relative to /api/v1 (BASE in lib/api.ts). All calls throw ApiError on failure.

/* ------------------------------------------------------------------ */
/* Shared types                                                        */
/* ------------------------------------------------------------------ */

export type Role = 'applicant' | 'alumni' | 'admin';
export type AccountStatus = 'pending' | 'active' | 'suspended';
export type JobType = 'internship' | 'fulltime' | 'parttime' | 'contract';
export type WorkMode = 'onsite' | 'hybrid' | 'remote';
export type JobStatus = 'open' | 'closed';
export type ApplicationStatus = 'submitted' | 'shortlisted' | 'accepted' | 'rejected' | 'withdrawn';
export type DocumentType = 'cv' | 'ktp' | 'intro_video';
export type TestimonialStatus = 'pending' | 'approved' | 'hidden';
export type AlumniState = 'pending' | 'approved' | 'rejected';

/** Cursor pagination used by every list that can be long. */
export type Page<T> = { items: T[]; next_cursor: string | null };
export type CursorQuery = { limit?: number; cursor?: string | null };

export type Skill = { id: string; name: string };

export type AccountUser = { id: string; username: string; role: Role; status: AccountStatus };

export type Verification = { state: AlumniState; reason: string | null };

/* ---- request bodies ---- */

export type LoginBody = { username: string; password: string };

export type ApplicantProfileBody = {
    full_name: string; // 1-200
    email: string;
    phone: string; // 8-15 digits, optional leading +
    nik: string; // exactly 16 digits
    address: string; // 1-500
    birth_date: string; // YYYY-MM-DD, age 15-100
    angkatan: number; // 1990..current year
    skill_ids: string[]; // 1-30, unique
    preferred_type?: JobType | null;
    preferred_location?: string | null; // max 100
};

export type RegisterBody = LoginBody & { profile: ApplicantProfileBody };

export type AlumniRegisterBody = LoginBody & {
    profile: { full_name: string; company: string; angkatan: number };
};

export type AlumniProfileBody = {
    full_name?: string | null;
    company?: string | null;
    angkatan?: number | null;
};

export type JobBody = {
    title: string;
    company: string;
    type: JobType;
    work_mode: WorkMode;
    location?: string | null;
    description: string;
    requirements?: string | null;
    deadline?: string | null; // YYYY-MM-DD, not in the past
    skill_ids?: string[]; // max 20, unique
};

export type ApplyBody = {
    cv_document_id: string;
    intro_video_document_id?: string | null;
    cover_note?: string | null; // max 2000
};

export type OwnerStatusBody = { status: 'shortlisted' | 'accepted' | 'rejected'; note?: string | null };
export type TestimonialBody = { application_id: string; content: string; show_name: boolean }; // content 20-1000

/* ---- responses ---- */

export type ApplicantProfile = {
    role: 'applicant';
    full_name: string;
    email: string;
    phone: string;
    nik: string;
    address: string;
    birth_date: string;
    angkatan: number;
    skills: Skill[];
    preferred_type: JobType | null;
    preferred_location: string | null;
};

export type AlumniProfile = {
    role: 'alumni';
    full_name: string | null;
    company: string | null;
    angkatan: number | null;
    profile_complete: boolean;
    verification: Verification;
};

export type DocumentItem = { id: string; type: DocumentType; ext: string; size: number; created_at: string };

export type JobSummary = {
    id: string;
    title: string;
    company: string;
    type: JobType;
    work_mode: WorkMode;
    location: string | null;
    deadline: string | null;
    status: JobStatus;
    skills: Skill[];
    created_at: string;
};

export type JobDetail = JobSummary & { description: string; requirements: string | null };

export type JobFilters = CursorQuery & {
    type?: JobType | '';
    work_mode?: WorkMode | '';
    q?: string; // max 100
    location?: string; // max 100
    skill?: string[]; // skill ids, max 20
};

export type StatusHistory = {
    from_status: ApplicationStatus | null;
    to_status: ApplicationStatus;
    note: string | null;
    created_at: string;
};

export type ApplicationSummary = { id: string; status: ApplicationStatus; created_at: string; job: JobSummary };

export type ApplicationDetail = {
    id: string;
    job: JobSummary;
    status: ApplicationStatus;
    cover_note: string | null;
    cv_document_id: string | null;
    intro_video_document_id: string | null;
    created_at: string;
    history: StatusHistory[];
};

export type OwnerDocument = { id: string; ext: string; size: number; created_at: string };

export type OwnerApplicant = {
    full_name: string;
    email: string;
    phone: string;
    angkatan: number;
    skills: Skill[];
};

export type OwnerApplication = {
    id: string;
    status: ApplicationStatus;
    created_at: string;
    applicant: OwnerApplicant | null;
    documents: { cv: OwnerDocument | null; video: OwnerDocument | null };
};

export type OwnerApplicationDetail = OwnerApplication & {
    job: JobSummary;
    cover_note: string | null;
    identity: { state: string; expires_at: string | null };
    history: StatusHistory[];
};

export type Identity = { nik: string; address: string; birth_date: string; ktp_available: boolean };

export type MatchItem = { job: JobSummary; score: number; matched_skills: Skill[] };

export type ApplicantDashboard = {
    applications: Record<ApplicationStatus, number>;
    documents: Record<DocumentType, number>;
    recent_applications: ApplicationSummary[];
    matches: MatchItem[];
};

export type OwnerDashboard = {
    jobs: Record<JobStatus, number>;
    applications: Record<ApplicationStatus, number>;
    new_applications: number;
};

export type PublicTestimonial = {
    id: string;
    content: string;
    created_at: string;
    author: { first_name: string | null; company: string | null } | null;
};

export type OwnTestimonial = {
    id: string;
    application_id: string;
    content: string;
    show_name: boolean;
    status: TestimonialStatus;
    created_at: string;
};

export type AdminTestimonial = OwnTestimonial & {
    author_id: string;
    display_first_name: string | null;
    display_company: string | null;
};

export type AdminAlumni = {
    id: string;
    username: string;
    account_status: AccountStatus;
    verification: Verification;
    full_name: string | null;
    company: string | null;
    angkatan: number | null;
    profile_complete: boolean;
    created_at: string;
};

export type AdminUser = {
    id: string;
    username: string;
    role: Role;
    status: AccountStatus;
    created_at: string;
    last_login_at: string | null;
};

export type AdminOverview = {
    users_by_role: Record<Role, number>;
    users_by_status: Record<AccountStatus, number>;
    jobs_by_status: Record<JobStatus, number>;
    applications_by_status: Record<ApplicationStatus, number>;
    documents_by_type: Record<DocumentType, number>;
    alumni_awaiting_decision: number;
};

/* ------------------------------------------------------------------ */
/* Endpoints                                                           */
/* ------------------------------------------------------------------ */

type Opts = { signal?: AbortSignal };

/** Raw URLs for file streams. Use as <a href>, <img src> or <video src>, not through api(). */
const FILES = '/api/v1';

export const auth = {
    /** Applicant sign-up with profile. Status becomes active immediately. */
    register: (body: RegisterBody) => api<AccountUser>('/auth/register', { method: 'POST', body }),
    /** Alumni sign-up. Account is pending until an admin approves it. */
    // registerAlumni: (body: LoginBody) => api<AccountUser>('/auth/register/alumni', { method: 'POST', body }),
    registerAlumni: (body: AlumniRegisterBody) => api<AccountUser>('/auth/register/alumni', { method: 'POST', body }),
    login: (body: LoginBody) => api<AccountUser>('/auth/login', { method: 'POST', body }),
    logout: () => api<{ ok: true }>('/auth/logout', { method: 'POST' }),
    me: (o?: Opts) => api<AccountUser>('/auth/me', o),
};

export const skills = {
    list: (o?: Opts) => api<Skill[]>('/skills', o),
};

export const profile = {
    get: (o?: Opts) => api<ApplicantProfile | AlumniProfile>('/me/profile', o),
    updateApplicant: (body: ApplicantProfileBody) =>
        api<ApplicantProfile>('/me/profile', { method: 'PUT', body }),
    updateAlumni: (body: AlumniProfileBody) => api<AlumniProfile>('/me/profile', { method: 'PUT', body }),
    /** Requires the current password. */
    deleteAccount: (password: string) =>
        api<{ ok: true }>('/me/account', { method: 'DELETE', body: { password } }),
};

export const documents = {
    list: (o?: Opts) => api<DocumentItem[]>('/me/documents', o),
    /** cv/ktp: pdf (ktp also jpg/png) up to 5 MiB, intro_video: mp4 up to 50 MiB. Max 5 per type, ktp is replaced. */
    upload: (type: DocumentType, file: File) => {
        const form = new FormData();
        form.append('type', type);
        form.append('file', file);
        return api<DocumentItem>('/me/documents', { method: 'POST', body: form });
    },
    downloadUrl: (id: string) => `${FILES}/me/documents/${id}/download`,
    remove: (id: string) => api<void>(`/me/documents/${id}`, { method: 'DELETE' }),
};

export const jobs = {
    list: (filters: JobFilters = {}, o?: Opts) => api<Page<JobSummary>>('/jobs', { query: filters, ...o }),
    get: (id: string, o?: Opts) => api<JobDetail>(`/jobs/${id}`, o),
    /** Jobs owned by the signed-in alumni/admin (max 200). */
    mine: (o?: Opts) => api<JobSummary[]>('/me/jobs', o),
    create: (body: JobBody) => api<JobDetail>('/jobs', { method: 'POST', body }),
    /** Owner only, and only while the job is open. */
    update: (id: string, body: JobBody) => api<JobDetail>(`/jobs/${id}`, { method: 'PUT', body }),
    close: (id: string) => api<JobDetail>(`/jobs/${id}/close`, { method: 'POST' }),
};

/** Applicant side. */
export const applications = {
    apply: (jobId: string, body: ApplyBody) =>
        api<ApplicationDetail>(`/jobs/${jobId}/apply`, { method: 'POST', body }),
    mine: (o?: Opts) => api<ApplicationSummary[]>('/me/applications', o),
    get: (id: string, o?: Opts) => api<ApplicationDetail>(`/me/applications/${id}`, o),
    /** Withdraws (soft): returns the application with status "withdrawn". */
    withdraw: (id: string) => api<ApplicationDetail>(`/me/applications/${id}`, { method: 'DELETE' }),
};

/** Vacancy owner side (alumni who own the job, or admin). */
export const owner = {
    applicants: (jobId: string, q: CursorQuery = {}, o?: Opts) =>
        api<Page<OwnerApplication>>(`/jobs/${jobId}/applications`, { query: q, ...o }),
    application: (id: string, o?: Opts) => api<OwnerApplicationDetail>(`/applications/${id}`, o),
    /** Allowed: submitted -> shortlisted/accepted/rejected, shortlisted -> accepted/rejected, accepted -> shortlisted/rejected. */
    setStatus: (id: string, body: OwnerStatusBody) =>
        api<OwnerApplicationDetail>(`/applications/${id}/status`, { method: 'PATCH', body }),
    identity: (id: string, o?: Opts) => api<Identity>(`/applications/${id}/identity`, o),
    cvUrl: (id: string) => `${FILES}/applications/${id}/cv`,
    videoUrl: (id: string) => `${FILES}/applications/${id}/video`,
    ktpUrl: (id: string) => `${FILES}/applications/${id}/identity/ktp`,
};

export const dashboard = {
    /** Applicant: jobs sharing at least one skill, best match first. */
    matches: (limit = 20, o?: Opts) => api<{ items: MatchItem[] }>('/me/matches', { query: { limit }, ...o }),
    applicant: (o?: Opts) => api<ApplicantDashboard>('/me/dashboard', o),
    owner: (o?: Opts) => api<OwnerDashboard>('/owner/dashboard', o),
};

export const testimonials = {
    /** Public, approved only. */
    list: (q: CursorQuery = {}, o?: Opts) => api<Page<PublicTestimonial>>('/testimonials', { query: q, ...o }),
    mine: (o?: Opts) => api<{ items: OwnTestimonial[] }>('/me/testimonials', o),
    /** Only for an accepted application, one per application. */
    create: (body: TestimonialBody) => api<OwnTestimonial>('/testimonials', { method: 'POST', body }),
    remove: (id: string) => api<void>(`/testimonials/${id}`, { method: 'DELETE' }),
};

export const admin = {
    overview: (o?: Opts) => api<AdminOverview>('/admin/overview', o),
    alumni: (q: CursorQuery & { state?: AlumniState } = {}, o?: Opts) =>
        api<Page<AdminAlumni>>('/admin/alumni', { query: q, ...o }),
    approveAlumni: (id: string) => api<AccountUser>(`/admin/alumni/${id}/approve`, { method: 'POST' }),
    rejectAlumni: (id: string, reason: string) =>
        api<AccountUser>(`/admin/alumni/${id}/reject`, { method: 'POST', body: { reason } }),
    users: (q: CursorQuery & { role?: Role; status?: AccountStatus; q?: string } = {}, o?: Opts) =>
        api<Page<AdminUser>>('/admin/users', { query: q, ...o }),
    setUserStatus: (id: string, status: 'active' | 'suspended') =>
        api<AdminUser>(`/admin/users/${id}/status`, { method: 'PATCH', body: { status } }),
    testimonials: (q: CursorQuery & { status?: TestimonialStatus } = {}, o?: Opts) =>
        api<Page<AdminTestimonial>>('/admin/testimonials', { query: q, ...o }),
    moderateTestimonial: (id: string, status: 'approved' | 'hidden') =>
        api<AdminTestimonial>(`/admin/testimonials/${id}`, { method: 'PATCH', body: { status } }),
};