'use client';

import { useState } from 'react';
import { Eye, EyeSlash } from '@phosphor-icons/react';
import { inputClass } from './FormField';

type Props = Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type' | 'className'>;

export default function PasswordInput(props: Props) {
    const [visible, setVisible] = useState(false);

    return (
        <div className="relative">
            <input {...props} type={visible ? 'text' : 'password'} className={`${inputClass} pr-12`} />
            <button
                type="button"
                onClick={() => setVisible((v) => !v)}
                aria-label={visible ? 'Hide password' : 'Show password'}
                aria-pressed={visible}
                className="absolute right-4 top-1/2 grid h-8 w-8 -translate-y-1/2 place-items-center rounded-full text-zinc-500 transition-colors hover:text-zinc-900"
            >
                {visible ? <EyeSlash size={18} weight="regular" /> : <Eye size={18} weight="regular" />}
            </button>
        </div>
    );
}