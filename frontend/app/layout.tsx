import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import Nav from '@/components/Nav';
import { AuthProvider } from '@/lib/auth';
import './globals.css';

const geist = Geist({ subsets: ['latin'], variable: '--font-sans', display: 'swap' });
const geistMono = Geist_Mono({ subsets: ['latin'], variable: '--font-mono', display: 'swap' });

export const metadata: Metadata = {
  title: 'TCancy',
  description: 'Jobs and internships for HMTC ITS alumni',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${geist.variable} ${geistMono.variable}`}>
      <body className="min-h-[100dvh] bg-zinc-50 font-sans text-zinc-900 antialiased">
        <AuthProvider>
          <Nav />
          <main className="mx-auto w-full max-w-7xl px-4 py-8 md:px-6">{children}</main>
        </AuthProvider>
      </body>
    </html>
  );
}