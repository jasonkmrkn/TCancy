'use client';

import { useCallback, useEffect, useState } from 'react';
import { Quotes } from '@phosphor-icons/react';
import Band, { SECTION_LABEL } from '@/components/home/Band';
import { api, ApiError } from '@/lib/api';
import { initials } from '@/lib/labels';

type Testimonial = {
  id: string;
  content: string;
  created_at: string;
  author: { first_name: string; company: string } | null;
};

const EASE = 'ease-[cubic-bezier(0.16,1,0.3,1)]';
const ROTATE_MS = 8000;

function Avatar({ name, size }: { name: string | null; size: 'sm' | 'lg' }) {
  return (
    <span
      className={`grid shrink-0 place-items-center rounded-full bg-zinc-200 font-medium text-zinc-700 ${size === 'lg' ? 'h-14 w-14 text-base' : 'h-11 w-11 text-sm'
        }`}
    >
      {initials(name)}
    </span>
  );
}

export default function Testimonials() {
  const [items, setItems] = useState<Testimonial[] | null>(null);
  const [error, setError] = useState('');
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);

  const load = useCallback(() => {
    setError('');
    setItems(null);
    api<{ items: Testimonial[] }>('/testimonials', { query: { limit: 6 } })
      .then((r) => {
        setItems(r.items);
        setActive(0);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load stories.'));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Auto-advance; pauses on hover/focus and is off entirely for reduced-motion users.
  const count = items?.length ?? 0;
  useEffect(() => {
    if (count < 2 || paused) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const id = window.setInterval(() => setActive((a) => (a + 1) % count), ROTATE_MS);
    return () => window.clearInterval(id);
  }, [count, paused, active]);

  const current = items && items.length > 0 ? items[Math.min(active, items.length - 1)] : null;

  return (
    <Band tone="muted">
      <div className="py-20">
        <p className={SECTION_LABEL}>Stories</p>
        <h2 className="mt-3 max-w-[20ch] text-4xl font-semibold leading-[1.05] tracking-tighter text-zinc-900">
          From classroom to workplace
        </h2>

        <div
          className="mt-12 grid gap-10 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] lg:gap-16"
          onMouseEnter={() => setPaused(true)}
          onMouseLeave={() => setPaused(false)}
          onFocus={() => setPaused(true)}
          onBlur={() => setPaused(false)}
        >
          {error && (
            <div role="alert" className="flex flex-col items-start gap-4 lg:col-span-2">
              <p className="text-sm text-red-700">{error}</p>
              <button
                onClick={load}
                className="min-h-10 rounded-full border border-zinc-200 bg-white px-5 text-sm font-medium text-zinc-900 transition hover:border-zinc-300 active:translate-y-[1px] active:scale-[0.98]"
              >
                Try again
              </button>
            </div>
          )}

          {!error && items === null && (
            <>
              <div aria-hidden className="h-72 animate-pulse rounded-[2.5rem] bg-white/70" />
              <div aria-hidden className="flex animate-pulse flex-col gap-4">
                {[0, 1, 2].map((i) => (
                  <div key={i} className="h-14 rounded-full bg-zinc-200/70" />
                ))}
              </div>
            </>
          )}

          {items && items.length === 0 && (
            <div className="rounded-[2.5rem] border border-zinc-200 bg-white p-10 lg:col-span-2">
              <p className="font-semibold tracking-tight text-zinc-900">No stories yet</p>
              <p className="mt-2 max-w-[48ch] text-sm leading-relaxed text-zinc-500">
                Stories appear here once an accepted applicant shares their experience and an admin approves it.
              </p>
            </div>
          )}

          {current && (
            <>
              <figure className="rounded-[2.5rem] border border-zinc-200/60 bg-white p-8 shadow-[0_20px_40px_-15px_rgba(24,24,27,0.08)] md:p-10">
                <Quotes size={40} weight="fill" className="text-zinc-300" aria-hidden />
                <div key={current.id} className="rise">
                  <blockquote className="mt-6 min-h-[9rem] text-2xl font-medium leading-snug tracking-tight text-zinc-900 md:text-[1.75rem]">
                    {current.content}
                  </blockquote>
                  <figcaption className="mt-8 flex items-center gap-4">
                    <Avatar name={current.author?.first_name ?? null} size="lg" />
                    <div>
                      <p className="font-semibold text-zinc-900">{current.author?.first_name ?? 'Anonymous'}</p>
                      {current.author?.company && <p className="text-sm text-zinc-500">{current.author.company}</p>}
                    </div>
                  </figcaption>
                </div>
              </figure>

              <ul className="self-start border-y border-zinc-300/70">
                {items!.map((t, i) => {
                  const on = i === active;
                  return (
                    <li key={t.id} className="relative border-b border-zinc-300/70 last:border-0">
                      <span
                        aria-hidden
                        className={`absolute inset-y-4 left-0 w-0.5 origin-center bg-zinc-900 transition duration-500 ${EASE} ${on ? 'scale-y-100 opacity-100' : 'scale-y-0 opacity-0'
                          }`}
                      />
                      <button
                        type="button"
                        aria-current={on}
                        onClick={() => setActive(i)}
                        className={`flex w-full items-center gap-4 px-4 py-5 text-left transition-colors duration-300 ${EASE} hover:bg-white/50`}
                      >
                        <Avatar name={t.author?.first_name ?? null} size="sm" />
                        <span className="min-w-0">
                          <span className={`block truncate font-medium ${on ? 'text-zinc-900' : 'text-zinc-600'}`}>
                            {t.author?.first_name ?? 'Anonymous'}
                          </span>
                          <span className="block truncate text-sm text-zinc-500">{t.author?.company ?? 'Applicant'}</span>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </>
          )}
        </div>
      </div>
    </Band>
  );
}