'use client';

import Link from 'next/link';
import { ArrowLeft } from '@phosphor-icons/react';
import JobForm, { emptyJob } from '@/components/JobForm';
import { NotAllowed, useIsOwnerRole } from '@/components/OwnerGate';
import { PageHeader } from '@/components/ui';

export default function NewJobPage() {
  const { loading, allowed } = useIsOwnerRole();

  if (loading) {
    return (
      <div aria-hidden className="flex animate-pulse flex-col gap-5 py-4">
        <div className="h-4 w-24 rounded-full bg-zinc-200/70" />
        <div className="h-12 w-80 max-w-full rounded-full bg-zinc-200/70" />
        <div className="mt-6 h-96 rounded-[2.5rem] bg-zinc-200/60" />
      </div>
    );
  }
  if (!allowed) return <NotAllowed />;

  return (
    <div className="py-4">
      <Link
        href="/jobs"
        className="mb-6 inline-flex items-center gap-1.5 text-sm font-medium text-zinc-600 transition-colors hover:text-zinc-900"
      >
        <ArrowLeft size={14} weight="bold" />
        My vacancies
      </Link>
      <PageHeader
        eyebrow="Vacancies"
        title="New vacancy"
        subtitle="Describe the role for the students after you. You can edit it until you close it."
      />
      <JobForm initial={emptyJob} />
    </div>
  );
}