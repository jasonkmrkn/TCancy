'use client';

import Link from 'next/link';
import JobForm, { emptyJob } from '@/components/JobForm';
import { NotAllowed, useIsOwnerRole } from '@/components/OwnerGate';

export default function NewJobPage() {
  const { loading, allowed } = useIsOwnerRole();
  if (loading) return <p className="text-sm text-gray-600">Loading...</p>;
  if (!allowed) return <NotAllowed />;
  return (
    <div>
      <Link href="/jobs" className="text-sm underline">
        Back to my vacancies
      </Link>
      <h1 className="mt-2 text-2xl font-semibold">New vacancy</h1>
      <JobForm initial={emptyJob} />
    </div>
  );
}
