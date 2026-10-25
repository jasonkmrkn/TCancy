'use client';

import Link from 'next/link';
import { useAuth } from '@/lib/auth';

export function useIsOwnerRole(): { loading: boolean; allowed: boolean } {
  const { user, loading } = useAuth();
  const allowed = !!user && user.status === 'active' && (user.role === 'alumni' || user.role === 'admin');
  return { loading, allowed };
}

export function NotAllowed() {
  const { user } = useAuth();
  return (
    <p className="text-sm">
      Only active alumni and admins can manage vacancies.{' '}
      {!user && (
        <Link href="/login" className="underline">
          Sign in
        </Link>
      )}
    </p>
  );
}
