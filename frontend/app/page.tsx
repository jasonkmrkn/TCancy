'use client';

import LatestJobs from '@/components/LatestJobs';
import SessionPanel from '@/components/SessionPanel';
import Testimonials from '@/components/Testimonials';
import { useAuth } from '@/lib/auth';

export default function HomePage() {
  const { user, loading } = useAuth();

  return (
    <div>
      <h1 className="text-2xl font-bold">TCancy</h1>
      <p className="mt-2 text-gray-600">Jobs and internships for HMTC ITS alumni.</p>
      {!loading && !user && (
        <div className="mt-6">
          <SessionPanel />
        </div>
      )}
      <LatestJobs />
      <Testimonials />
    </div>
  );
}
