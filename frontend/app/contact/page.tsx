'use client';

import { useState } from 'react';
import { CheckCircle, Clock, Envelope, MapPin, PaperPlaneTilt, Phone } from '@phosphor-icons/react';
import { stagger } from '@/components/AuthShell';
import FormField, { inputClass } from '@/components/FormField';
import { SECTION_LABEL } from '@/components/home/Band';

// EDIT THESE: contact details shown on the page. The email address is a placeholder;
// the phone, office and hours come from the design reference and need to be verified.
const CONTACT = {
  email: 'hello@tcancy.id',
  phone: '+62 31 5947 218',
  office: 'Informatics Engineering Building, 2nd floor, Keputih, Sukolilo, Surabaya',
  hours: 'Monday to Friday, 08:30 to 16:00 WIB',
};

const DETAILS = [
  { Icon: Envelope, label: 'Email', value: CONTACT.email, href: `mailto:${CONTACT.email}` },
  { Icon: Phone, label: 'Phone', value: CONTACT.phone, href: `tel:${CONTACT.phone.replace(/[^\d+]/g, '')}` },
  { Icon: MapPin, label: 'Office', value: CONTACT.office },
  { Icon: Clock, label: 'Hours', value: CONTACT.hours },
];

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MAX_MESSAGE = 2000;

export default function ContactPage() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [fields, setFields] = useState<Record<string, string>>({});
  const [sent, setSent] = useState(false);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (!name.trim()) errs.name = 'Name is required.';
    if (!email.trim()) errs.email = 'Email is required.';
    else if (!EMAIL_RE.test(email.trim())) errs.email = 'Enter a valid email address.';
    if (!subject.trim()) errs.subject = 'Topic is required.';
    if (message.trim().length < 10) errs.message = 'Message must be at least 10 characters.';
    else if (message.length > MAX_MESSAGE) errs.message = `Message must be at most ${MAX_MESSAGE} characters.`;
    setFields(errs);
    if (Object.keys(errs).length > 0) {
      requestAnimationFrame(() => {
        document.querySelector<HTMLElement>('[data-invalid="true"] :is(input, textarea)')?.focus();
      });
      return;
    }
    // TODO: the backend has no contact endpoint yet, so this only validates and shows the success state.
    setSent(true);
  }

  function reset() {
    setName('');
    setEmail('');
    setSubject('');
    setMessage('');
    setFields({});
    setSent(false);
  }

  return (
    <div className="grid items-start gap-12 py-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:gap-20">
      {/* Left: intro + contact details */}
      <div>
        <header className="rise" style={stagger(0)}>
          <p className={SECTION_LABEL}>Contact us</p>
          <h1 className="mt-3 max-w-[16ch] text-4xl font-semibold leading-[1.05] tracking-tighter text-zinc-900 md:text-5xl">
            Questions about your account or a vacancy?
          </h1>
          <p className="mt-5 max-w-[52ch] leading-relaxed text-zinc-500">
            The admin team replies within one business day. For alumni account approval, mention your class year to speed things up.
          </p>
        </header>

        <ul className="rise mt-10 divide-y divide-zinc-200 border-y border-zinc-200" style={stagger(1)}>
          {DETAILS.map(({ Icon, label, value, href }) => (
            <li key={label} className="flex items-start gap-5 py-5">
              <span className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-zinc-200/70 text-zinc-700">
                <Icon size={22} weight="regular" />
              </span>
              <div className="min-w-0">
                <p className={SECTION_LABEL}>{label}</p>
                {href ? (
                  <a
                    href={href}
                    className="mt-1 block text-lg tracking-tight text-zinc-900 underline-offset-4 hover:underline"
                  >
                    {value}
                  </a>
                ) : (
                  <p className="mt-1 text-lg leading-snug tracking-tight text-zinc-900">{value}</p>
                )}
              </div>
            </li>
          ))}
        </ul>
      </div>

      {/* Right: form card */}
      <div
        className="rise rounded-[2.5rem] border border-zinc-200/60 bg-white p-8 shadow-[0_20px_40px_-15px_rgba(24,24,27,0.08)] md:p-10"
        style={stagger(2)}
      >
        {sent ? (
          <div role="status" className="flex flex-col items-start gap-4 py-6">
            <span className="grid h-12 w-12 place-items-center rounded-full bg-zinc-100 text-zinc-900">
              <CheckCircle size={26} weight="regular" />
            </span>
            <h2 className="text-2xl font-semibold tracking-tight text-zinc-900">Thank you, {name.trim()}.</h2>
            <p className="max-w-[40ch] leading-relaxed text-zinc-500">Your message has been recorded.</p>
            <button
              onClick={reset}
              className="mt-2 min-h-11 rounded-full border border-zinc-200 bg-white px-6 text-sm font-medium text-zinc-900 transition duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] hover:border-zinc-300 active:translate-y-[1px] active:scale-[0.98]"
            >
              Send another message
            </button>
          </div>
        ) : (
          <form className="flex flex-col gap-5" onSubmit={submit} noValidate>
            <div className="grid items-start gap-5 sm:grid-cols-2">
              <FormField label="Name" error={fields.name}>
                <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
              </FormField>
              <FormField label="Email" error={fields.email}>
                <input
                  className={inputClass}
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                />
              </FormField>
            </div>
            <FormField label="Topic" error={fields.subject} hint="Example: alumni account approval, file upload problem.">
              <input className={inputClass} value={subject} onChange={(e) => setSubject(e.target.value)} />
            </FormField>
            <FormField label="Message" error={fields.message} hint={`${message.length} of ${MAX_MESSAGE} characters`}>
              <textarea
                className={`${inputClass} resize-y`}
                rows={6}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
              />
            </FormField>
            <div>
              <button
                type="submit"
                className="inline-flex min-h-12 items-center gap-2 rounded-full bg-zinc-900 px-6 text-sm font-medium text-zinc-50 shadow-[inset_0_1px_0_rgba(255,255,255,0.12)] transition duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] hover:bg-zinc-800 active:translate-y-[1px] active:scale-[0.98] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900"
              >
                <PaperPlaneTilt size={18} weight="regular" />
                Send message
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}