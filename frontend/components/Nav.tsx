'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { CaretDown, List, SignOut, X } from '@phosphor-icons/react';
import { useAuth, type User } from '@/lib/auth';

type Item = { href: string; label: string };

// Centered links, always visible.
export const PUBLIC: Item[] = [
  { href: '/', label: 'Home' },
  { href: '/vacancy', label: 'Vacancies' },
  { href: '/contact', label: 'Contact' },
];

// Role-specific links, shown in the account dropdown once signed in.
export function accountMenuFor(user: User | null): Item[] {
  if (!user) return [];
  if (user.status !== 'active') return [{ href: '/profile', label: 'Profile' }];
  if (user.role === 'applicant') {
    return [
      { href: '/dashboard', label: 'Dashboard' },
      { href: '/applications', label: 'My applications' },
      { href: '/documents', label: 'Documents' },
      { href: '/profile', label: 'Profile' },
    ];
  }
  if (user.role === 'alumni') {
    return [
      { href: '/dashboard', label: 'Dashboard' },
      { href: '/jobs', label: 'My vacancies' },
      { href: '/profile', label: 'Profile' },
    ];
  }
  return [
    { href: '/dashboard', label: 'Dashboard' },
    // { href: '/jobs', label: 'My vacancies' },
    { href: '/admin', label: 'Admin' },
  ];
}

function isActive(pathname: string, href: string) {
  return href === '/' ? pathname === '/' : pathname === href || pathname.startsWith(`${href}/`);
}

const EASE = 'ease-[cubic-bezier(0.16,1,0.3,1)]';
const PUSH = 'active:translate-y-[1px] active:scale-[0.98]';

function Logo() {
  return (
    <Link
      href="/"
      className={`group flex items-baseline gap-0.5 text-[1.375rem] font-semibold tracking-tighter text-zinc-900 transition-opacity duration-300 ${EASE} hover:opacity-80`}
    >
      TCancy
      <span
        aria-hidden
        className={`h-1.5 w-1.5 rounded-[2px] bg-emerald-600 transition-transform duration-500 ${EASE} group-hover:rotate-90`}
      />
    </Link>
  );
}

function AccountMenu({ user, items, onLogout }: { user: User; items: Item[]; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const pathname = usePathname();

  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="menu"
        className={`flex items-center gap-2.5 rounded-full border border-zinc-200 bg-white py-1 pl-1 pr-3 text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] transition duration-300 ${EASE} hover:border-zinc-300 ${PUSH} focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-600`}
      >
        <span className="grid h-7 w-7 place-items-center rounded-full bg-zinc-900 text-xs font-medium uppercase text-zinc-50">
          {user.username.slice(0, 1)}
        </span>
        <span className="font-medium text-zinc-900">{user.username}</span>
        <span className="font-mono text-[10px] uppercase tracking-wider text-zinc-500">{user.role}</span>
        <CaretDown
          size={14}
          weight="regular"
          className={`text-zinc-500 transition-transform duration-300 ${EASE} ${open ? 'rotate-180' : ''}`}
        />
      </button>

      <div
        role="menu"
        aria-hidden={!open}
        className={`absolute right-0 mt-2 w-56 origin-top-right rounded-2xl border border-zinc-200/70 bg-white p-1.5 shadow-[0_20px_40px_-15px_rgba(24,24,27,0.12)] transition duration-300 ${EASE} ${open ? 'visible translate-y-0 scale-100 opacity-100' : 'invisible -translate-y-1 scale-95 opacity-0'
          }`}
      >
        {items.map((it) => (
          <Link
            key={it.href}
            href={it.href}
            role="menuitem"
            tabIndex={open ? 0 : -1}
            className="block rounded-xl px-3 py-2 text-sm text-zinc-700 transition-colors hover:bg-zinc-100 hover:text-zinc-900"
          >
            {it.label}
          </Link>
        ))}
        <div className="my-1.5 border-t border-zinc-100" />
        <button
          role="menuitem"
          tabIndex={open ? 0 : -1}
          onClick={onLogout}
          className={`flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-zinc-600 transition-colors hover:bg-zinc-100 hover:text-zinc-900 ${PUSH}`}
        >
          <SignOut size={16} weight="regular" />
          Sign out
        </button>
      </div>
    </div>
  );
}

function AuthSkeleton() {
  return <div aria-hidden className="h-9 w-36 animate-pulse rounded-full bg-zinc-100" />;
}

export default function Nav() {
  const { user, loading, logout } = useAuth();
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const account = loading ? [] : accountMenuFor(user);

  useEffect(() => setMobileOpen(false), [pathname]);

  return (
    <header className="sticky top-0 z-40 border-b border-zinc-200/70 bg-white/80 shadow-[inset_0_-1px_0_rgba(255,255,255,0.6)] backdrop-blur-xl">
      <nav className="mx-auto grid h-16 w-full max-w-7xl grid-cols-[auto_1fr_auto] items-center gap-4 px-4 md:grid-cols-[1fr_auto_1fr] md:px-6">
        {/* Left: logo */}
        <div className="justify-self-start">
          <Logo />
        </div>

        {/* Center: main links (desktop) */}
        <ul className="hidden items-center gap-1 md:flex">
          {PUBLIC.map((it) => {
            const active = isActive(pathname, it.href);
            return (
              <li key={it.href}>
                <Link
                  href={it.href}
                  aria-current={active ? 'page' : undefined}
                  className={`relative block px-4 py-2 text-sm font-medium transition-colors duration-300 ${EASE} ${active ? 'text-zinc-900' : 'text-zinc-500 hover:text-zinc-900'
                    }`}
                >
                  {it.label}
                  <span
                    aria-hidden
                    className={`absolute inset-x-4 -bottom-[13px] h-0.5 origin-left bg-emerald-600 transition-transform duration-500 ${EASE} ${active ? 'scale-x-100' : 'scale-x-0'
                      }`}
                  />
                </Link>
              </li>
            );
          })}
        </ul>

        {/* Right: auth */}
        <div className="flex items-center gap-2 justify-self-end">
          <div className="hidden items-center gap-1 md:flex">
            {loading && <AuthSkeleton />}
            {!loading && !user && (
              <>
                <Link
                  href="/login"
                  className={`rounded-full px-4 py-2 text-sm font-medium text-zinc-600 transition-colors hover:text-zinc-900 ${PUSH}`}
                >
                  Sign in
                </Link>
                <Link
                  href="/register"
                  className={`rounded-full bg-zinc-900 px-4 py-2 text-sm font-medium text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.15)] transition duration-300 ${EASE} hover:bg-zinc-800 ${PUSH}`}
                >
                  Register
                </Link>
              </>
            )}
            {user && <AccountMenu user={user} items={account} onLogout={() => logout()} />}
          </div>

          {/* Mobile toggle */}
          <button
            className={`grid h-10 w-10 place-items-center rounded-full border border-zinc-200 bg-white text-zinc-900 md:hidden ${PUSH}`}
            aria-label={mobileOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={mobileOpen}
            onClick={() => setMobileOpen((o) => !o)}
          >
            {mobileOpen ? <X size={18} weight="regular" /> : <List size={18} weight="regular" />}
          </button>
        </div>
      </nav>

      {/* Mobile panel */}
      <div
        className={`grid transition-[grid-template-rows] duration-500 ${EASE} md:hidden ${mobileOpen ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'
          }`}
      >
        <div className="overflow-hidden">
          <div className="border-t border-zinc-200/70 px-4 pb-4 pt-2">
            <ul className="flex flex-col">
              {PUBLIC.map((it) => {
                const active = isActive(pathname, it.href);
                return (
                  <li key={it.href} className="border-b border-zinc-100 last:border-0">
                    <Link
                      href={it.href}
                      tabIndex={mobileOpen ? 0 : -1}
                      className={`flex items-center justify-between py-3 text-base font-medium ${active ? 'text-zinc-900' : 'text-zinc-500'
                        }`}
                    >
                      {it.label}
                      {active && <span aria-hidden className="h-1.5 w-1.5 rounded-[2px] bg-emerald-600" />}
                    </Link>
                  </li>
                );
              })}
            </ul>

            <div className="mt-3 border-t border-zinc-200/70 pt-4">
              {loading && <AuthSkeleton />}
              {!loading && !user && (
                <div className="grid grid-cols-2 gap-2">
                  <Link
                    href="/login"
                    tabIndex={mobileOpen ? 0 : -1}
                    className={`rounded-full border border-zinc-200 bg-white px-4 py-2.5 text-center text-sm font-medium text-zinc-900 ${PUSH}`}
                  >
                    Sign in
                  </Link>
                  <Link
                    href="/register"
                    tabIndex={mobileOpen ? 0 : -1}
                    className={`rounded-full bg-zinc-900 px-4 py-2.5 text-center text-sm font-medium text-white ${PUSH}`}
                  >
                    Register
                  </Link>
                </div>
              )}
              {user && (
                <div className="flex flex-col">
                  <p className="pb-2 font-mono text-[11px] uppercase tracking-wider text-zinc-500">
                    {user.username} / {user.role}
                  </p>
                  {account.map((it) => (
                    <Link
                      key={it.href}
                      href={it.href}
                      tabIndex={mobileOpen ? 0 : -1}
                      className="py-2 text-sm text-zinc-700"
                    >
                      {it.label}
                    </Link>
                  ))}
                  <button
                    onClick={() => logout()}
                    tabIndex={mobileOpen ? 0 : -1}
                    className={`mt-1 flex items-center gap-2 py-2 text-left text-sm text-zinc-600 ${PUSH}`}
                  >
                    <SignOut size={16} weight="regular" />
                    Sign out
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}