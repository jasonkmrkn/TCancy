"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Check, FilePdf, FileVideo } from "@phosphor-icons/react";
import FormField, { FormAlert, textareaClass } from "@/components/FormField";
import { BTN_PRIMARY, EASE } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

/**
 * Consent scopes for POST /jobs/{id}/apply (backend: REQUIRED_CONSENTS = profile, cv;
 * `video` is also required when an intro video is attached).
 */
const CONSENT_LABELS: Record<string, string> = {
  profile:
    "I agree to share my profile details (name, email, phone, address and skills) with the vacancy owner.",
  cv: "I agree to share my CV with the vacancy owner.",
  video: "I agree to share my intro video with the vacancy owner.",
};

type Doc = {
  id: string;
  type: "cv" | "ktp" | "intro_video";
  ext: string;
  size: number;
  created_at: string;
};

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function formatSize(n: number): string {
  if (n >= 1024 * 1024) return (n / (1024 * 1024)).toFixed(1) + " MB";
  if (n >= 1024) return Math.round(n / 1024) + " KB";
  return n + " B";
}

/** One selectable file, shown as a radio card. */
function DocOption({
  doc,
  name,
  checked,
  onChange,
  icon: Icon,
  label,
}: {
  doc: Doc;
  name: string;
  checked: boolean;
  onChange: () => void;
  icon: React.ElementType;
  label: string;
}) {
  return (
    <label
      className={`flex cursor-pointer items-center gap-3 rounded-2xl border px-4 py-3 transition duration-300 ${EASE} focus-within:ring-4 focus-within:ring-zinc-900/10 ${checked
          ? "border-zinc-900 bg-zinc-50"
          : "border-zinc-200 bg-white hover:border-zinc-400"
        }`}
    >
      <input
        type="radio"
        name={name}
        checked={checked}
        onChange={onChange}
        className="sr-only"
      />
      <span
        aria-hidden
        className={`grid h-9 w-9 shrink-0 place-items-center rounded-full ${checked ? "bg-zinc-900 text-zinc-50" : "bg-zinc-100 text-zinc-700"}`}
      >
        <Icon size={18} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-medium text-zinc-900">
          {label} · {formatDate(doc.created_at)}
        </span>
        <span className="block font-mono text-xs text-zinc-500">
          {doc.ext.replace(/^\./, "").toUpperCase()} · {formatSize(doc.size)}
        </span>
      </span>
      <span
        aria-hidden
        className={`h-4 w-4 shrink-0 rounded-full border ${checked ? "border-[5px] border-zinc-900 bg-white" : "border-zinc-300"}`}
      />
    </label>
  );
}

export default function ApplyForm({ jobId }: { jobId: string }) {
  const router = useRouter();
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const [cv, setCv] = useState("");
  const [video, setVideo] = useState("");
  const [note, setNote] = useState("");
  const [agreed, setAgreed] = useState<string[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<Doc[]>("/me/documents")
      .then((list) => {
        setDocs(list);
        const cvs = list.filter((d) => d.type === "cv");
        if (cvs.length === 1) setCv(cvs[0].id);
      })
      .catch((e) => {
        setDocs([]);
        setError(
          e instanceof ApiError ? e.message : "Could not load your documents.",
        );
      });
  }, []);

  const cvs = (docs ?? []).filter((d) => d.type === "cv");
  const videos = (docs ?? []).filter((d) => d.type === "intro_video");
  const required = video ? ["profile", "cv", "video"] : ["profile", "cv"];

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const errs: Record<string, string> = {};
    if (!cv) errs.cv_document_id = "Choose a CV.";
    if (note.length > 2000)
      errs.cover_note = "The cover note can have at most 2000 characters.";
    if (required.some((v) => !agreed.includes(v)))
      errs.consents = "Please accept all the statements to apply.";
    setErrors(errs);
    if (Object.keys(errs).length) return;
    const body: Record<string, string | string[]> = {
      cv_document_id: cv,
      consents: required.filter((v) => agreed.includes(v)),
    };
    if (video) body.intro_video_document_id = video;
    if (note.trim()) body.cover_note = note.trim();
    setBusy(true);
    try {
      const res = await api<{ id: string }>(`/jobs/${jobId}/apply`, {
        method: "POST",
        body,
      });
      router.push(`/applications/${res.id}`);
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fields).length) {
        setErrors(err.fields);
        setError(err.message);
      } else {
        setError(
          err instanceof ApiError
            ? err.message
            : "Could not submit the application.",
        );
      }
      setBusy(false);
    }
  }

  const card =
    "rounded-[2.5rem] border border-zinc-200/60 bg-white p-8 shadow-[0_20px_40px_-15px_rgba(24,24,27,0.08)]";

  if (!docs) {
    return (
      <div aria-hidden className={`${card} animate-pulse`}>
        <div className="h-6 w-48 rounded-full bg-zinc-200/70" />
        <div className="mt-6 h-16 rounded-2xl bg-zinc-200/60" />
        <div className="mt-3 h-24 rounded-2xl bg-zinc-200/60" />
      </div>
    );
  }

  return (
    <form
      onSubmit={submit}
      noValidate
      className={`${card} flex flex-col gap-6`}
    >
      <div>
        <h2 className="text-xl font-semibold tracking-tight text-zinc-900">
          Apply for this vacancy
        </h2>
        <p className="mt-1 text-sm text-zinc-500">
          Pick the files to send. The alumnus who posted it will review your
          application.
        </p>
      </div>

      <fieldset
        className="flex flex-col gap-2 text-sm"
        data-invalid={errors.cv_document_id ? "true" : undefined}
      >
        <legend className="mb-2 font-medium text-zinc-900">CV</legend>
        {cvs.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-zinc-300 px-4 py-4 text-zinc-600">
            You need to upload a CV before applying.{" "}
            <Link
              href="/documents"
              className="font-medium text-zinc-900 underline underline-offset-4"
            >
              Go to Documents
            </Link>
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {cvs.map((d) => (
              <DocOption
                key={d.id}
                doc={d}
                name="cv"
                checked={cv === d.id}
                onChange={() => setCv(d.id)}
                icon={FilePdf}
                label="CV"
              />
            ))}
          </div>
        )}
        {errors.cv_document_id && (
          <p role="alert" className="text-[13px] text-red-700">
            {errors.cv_document_id}
          </p>
        )}
      </fieldset>

      {videos.length > 0 && (
        <fieldset className="flex flex-col gap-2 text-sm">
          <legend className="mb-2 font-medium text-zinc-900">
            Intro video{" "}
            <span className="font-normal text-zinc-500">(optional)</span>
          </legend>
          <div className="flex flex-col gap-2">
            {videos.map((d) => (
              <DocOption
                key={d.id}
                doc={d}
                name="video"
                checked={video === d.id}
                onChange={() => setVideo(d.id)}
                icon={FileVideo}
                label="Video"
              />
            ))}
            {video && (
              <button
                type="button"
                onClick={() => setVideo("")}
                className="self-start text-[13px] font-medium text-zinc-600 underline-offset-4 hover:text-zinc-900 hover:underline"
              >
                Remove video
              </button>
            )}
          </div>
          {errors.intro_video_document_id && (
            <p role="alert" className="text-[13px] text-red-700">
              {errors.intro_video_document_id}
            </p>
          )}
        </fieldset>
      )}

      <div className="flex flex-col gap-2">
        <FormField
          label="Cover note"
          error={errors.cover_note}
          hint="Optional."
        >
          <textarea
            className={textareaClass}
            rows={5}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Why are you a good fit for this role?"
          />
        </FormField>
        <div className="-mt-1 flex justify-end">
          <span
            className={`font-mono text-xs ${note.length > 2000 ? "text-red-700" : "text-zinc-400"}`}
          >
            {note.length}/2000
          </span>
        </div>
      </div>

      <fieldset
        className="flex flex-col gap-3 text-sm"
        data-invalid={errors.consents ? "true" : undefined}
      >
        <legend className="mb-1 font-medium text-zinc-900">Consent</legend>
        {required.map((value) => {
          const checked = agreed.includes(value);
          return (
            <label
              key={value}
              className={`flex cursor-pointer items-start gap-3 rounded-2xl border px-4 py-3 transition duration-300 ${EASE} focus-within:ring-4 focus-within:ring-zinc-900/10 ${checked
                  ? "border-zinc-900 bg-zinc-50"
                  : "border-zinc-200 bg-white hover:border-zinc-400"
                }`}
            >
              <input
                type="checkbox"
                className="sr-only"
                checked={checked}
                onChange={() =>
                  setAgreed((cur) =>
                    checked ? cur.filter((v) => v !== value) : [...cur, value],
                  )
                }
              />
              <span
                aria-hidden
                className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-md border ${checked
                    ? "border-zinc-900 bg-zinc-900 text-zinc-50"
                    : "border-zinc-300 bg-white"
                  }`}
              >
                {checked && <Check size={12} weight="bold" />}
              </span>
              <span className="leading-relaxed text-zinc-700">
                {CONSENT_LABELS[value]}
              </span>
            </label>
          );
        })}
        {errors.consents && (
          <p role="alert" className="text-[13px] text-red-700">
            {errors.consents}
          </p>
        )}
      </fieldset>

      {error && <FormAlert>{error}</FormAlert>}

      <button
        type="submit"
        disabled={busy || cvs.length === 0}
        className={`${BTN_PRIMARY} w-full`}
      >
        {busy ? "Submitting..." : "Submit application"}
      </button>
    </form>
  );
}