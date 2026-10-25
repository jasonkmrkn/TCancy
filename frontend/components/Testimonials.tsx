'use client';

import { useEffect, useState } from 'react';
import { api, ApiError } from '@/lib/api';

type Testimonial = {
  id: string;
  content: string;
  created_at: string;
  author: { first_name: string; company: string } | null;
};

export default function Testimonials() {
  const [items, setItems] = useState<Testimonial[] | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api<{ items: Testimonial[] }>('/testimonials', { query: { limit: 6 } })
      .then((r) => setItems(r.items))
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load testimonials.'));
  }, []);

  return (
    <section className="mt-8">
      <h2 className="text-xl font-semibold">Testimonials</h2>
      {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
      {!error && items === null && <p className="mt-2 text-sm text-gray-600">Loading...</p>}
      {items && items.length === 0 && <p className="mt-2 text-sm text-gray-600">No testimonials yet.</p>}
      {items && items.length > 0 && (
        <ul className="mt-3 grid gap-3 sm:grid-cols-2">
          {items.map((t) => (
            <li key={t.id} className="rounded border p-3 text-sm">
              <p>&ldquo;{t.content}&rdquo;</p>
              <p className="mt-2 text-gray-600">
                {t.author ? `${t.author.first_name}, ${t.author.company}` : 'Anonymous'}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
