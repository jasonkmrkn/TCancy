'use client';

import { useState } from 'react';
import FormField, { inputClass } from '@/components/FormField';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

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
    if (!subject.trim()) errs.subject = 'Subject is required.';
    if (message.trim().length < 10) errs.message = 'Message must be at least 10 characters.';
    else if (message.length > 2000) errs.message = 'Message must be at most 2000 characters.';
    setFields(errs);
    if (Object.keys(errs).length > 0) return;
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
    <div className="max-w-lg text-sm">
      <h1 className="text-2xl font-bold">Contact</h1>
      <p className="mt-2 text-gray-600">Have a question about TCancy? Fill in the form below.</p>
      {sent ? (
        <div className="mt-4">
          <p role="status" className="rounded border border-green-700 px-3 py-2 text-green-800">
            Thank you, {name.trim()}. Your message has been recorded.
          </p>
          <button className="mt-3 rounded border px-3 py-1" onClick={reset}>
            Send another message
          </button>
        </div>
      ) : (
        <form className="mt-4 space-y-3" onSubmit={submit} noValidate>
          <FormField label="Name" error={fields.name}>
            <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} />
          </FormField>
          <FormField label="Email" error={fields.email}>
            <input
              className={inputClass}
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </FormField>
          <FormField label="Subject" error={fields.subject}>
            <input
              className={inputClass}
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
            />
          </FormField>
          <FormField label="Message" error={fields.message}>
            <textarea
              className={inputClass}
              rows={6}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
            />
          </FormField>
          <button type="submit" className="rounded border px-3 py-1">
            Send message
          </button>
        </form>
      )}
    </div>
  );
}
