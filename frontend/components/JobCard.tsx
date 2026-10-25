import Link from 'next/link';

export type Job = {
  id: string;
  title: string;
  company: string;
  type: string;
  work_mode: string;
  location: string | null;
  deadline: string | null;
  status: string;
  skills: { id: string; name: string }[];
  created_at: string;
};

export default function JobCard({ job, extra }: { job: Job; extra?: React.ReactNode }) {
  return (
    <li className="p-3 text-sm">
      <Link href={`/vacancy/${job.id}`} className="font-medium underline">
        {job.title}
      </Link>
      {job.status === 'closed' && <span className="ml-2 text-xs text-gray-500">(closed)</span>}
      <p className="text-gray-700">
        {job.company} · {job.type} · {job.work_mode}
        {job.location ? ` · ${job.location}` : ''}
      </p>
      {job.deadline && <p className="text-gray-500">Deadline: {job.deadline}</p>}
      {job.skills.length > 0 && <p className="text-gray-500">{job.skills.map((s) => s.name).join(', ')}</p>}
      {extra}
    </li>
  );
}
