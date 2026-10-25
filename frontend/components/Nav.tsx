'use client';

import Link from 'next/link';
import { useAuth, type User } from '@/lib/auth';

type Item = { href: string; label: string };

const PUBLIC: Item[] = [
  { href: '/', label: 'Home' },
  { href: '/vacancy', label: 'Vacancies' },
  { href: '/contact', label: 'Contact' },
];

export function menuFor(user: User | null): Item[] {
  if (!user) {
    return [...PUBLIC, { href: '/login', label: 'Sign in' }, { href: '/register', label: 'Register' }];
  }
  if (user.status !== 'active') {
    return [...PUBLIC, { href: '/profile', label: 'Profile' }];
  }
  if (user.role === 'applicant') {
    return [
      ...PUBLIC,
      { href: '/dashboard', label: 'Dashboard' },
      { href: '/applications', label: 'My applications' },
      { href: '/documents', label: 'Documents' },
      { href: '/profile', label: 'Profile' },
    ];
  }
  if (user.role === 'alumni') {
    return [
      ...PUBLIC,
      { href: '/dashboard', label: 'Dashboard' },
      { href: '/jobs', label: 'My vacancies' },
      { href: '/profile', label: 'Profile' },
    ];
  }
  return [
    ...PUBLIC,
    { href: '/dashboard', label: 'Dashboard' },
    { href: '/jobs', label: 'My vacancies' },
    { href: '/admin', label: 'Admin' },
  ];
}

export default function Nav() {
  const { user, loading, logout } = useAuth();
  const items = loading ? PUBLIC : menuFor(user);

  return (
    <nav className="border-b">
      <div className="mx-auto flex max-w-4xl flex-wrap items-center gap-4 p-4 text-sm">
        <Link href="/" className="text-lg font-bold">
          TCancy
        </Link>
        <ul className="flex flex-wrap gap-3">
          {items.map((it) => (
            <li key={it.href}>
              <Link href={it.href} className="text-gray-700 hover:underline">
                {it.label}
              </Link>
            </li>
          ))}
        </ul>
        {user && (
          <div className="ml-auto flex items-center gap-3">
            <span className="text-gray-600">
              {user.username} ({user.role})
            </span>
            <button className="rounded border px-3 py-1" onClick={() => logout()}>
              Sign out
            </button>
          </div>
        )}
      </div>
    </nav>
  );
}
