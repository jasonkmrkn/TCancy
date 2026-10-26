import Hero from '@/components/home/Hero';
import TrustStrip from '@/components/home/TrustStrip';
import LatestJobs from '@/components/LatestJobs';
import Testimonials from '@/components/Testimonials';

export default function HomePage() {
  return (
    <>
      <Hero />
      <TrustStrip />
      <LatestJobs />
      <Testimonials />
    </>
  );
}