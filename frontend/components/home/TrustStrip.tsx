import { ArrowUUpLeft, LockKey, UsersThree } from '@phosphor-icons/react/dist/ssr';
import Band from './Band';

// Each line describes behaviour that exists in the backend.
const ITEMS = [
    { Icon: UsersThree, title: 'Posted by alumni', text: 'Every poster is an alumnus approved by an admin.' },
    {
        Icon: LockKey,
        title: 'Scoped data access',
        text: 'Your NIK and ID card are visible only to the owner of a vacancy you apply to.',
    },
    { Icon: ArrowUUpLeft, title: 'Withdraw anytime', text: 'Pull an application back any time before a final decision.' },
];

export default function TrustStrip() {
    return (
        <Band tone="white">
            <ul className="grid divide-y divide-zinc-200 md:grid-cols-3 md:divide-x md:divide-y-0">
                {ITEMS.map(({ Icon, title, text }) => (
                    <li key={title} className="flex items-start gap-4 py-7 md:px-8 md:first:pl-0 md:last:pr-0">
                        <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-zinc-100 text-zinc-700">
                            <Icon size={22} weight="regular" />
                        </span>
                        <div>
                            <h3 className="font-semibold tracking-tight text-zinc-900">{title}</h3>
                            <p className="mt-1 text-sm leading-relaxed text-zinc-500">{text}</p>
                        </div>
                    </li>
                ))}
            </ul>
        </Band>
    );
}