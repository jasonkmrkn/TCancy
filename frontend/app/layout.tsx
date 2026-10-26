import type { Metadata } from 'next';
import { Geist_Mono, Plus_Jakarta_Sans } from 'next/font/google';
import Footer from '@/components/Footer';
import Nav from '@/components/Nav';
import PageShell from '@/components/PageShell';
import { AuthProvider } from '@/lib/auth';
import './globals.css';

const jakarta = Plus_Jakarta_Sans({ subsets: ['latin'], variable: '--font-sans', display: 'swap' });
const geistMono = Geist_Mono({ subsets: ['latin'], variable: '--font-mono', display: 'swap' });

export const metadata: Metadata = {
  title: 'TCancy',
  description: 'Jobs and internships for HMTC ITS alumni',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${jakarta.variable} ${geistMono.variable}`}>
      <body className="flex min-h-[100dvh] flex-col bg-zinc-50 font-sans text-zinc-900 antialiased">
        <AuthProvider>
          <Nav />
          <main className="flex-1">
            <PageShell>{children}</PageShell>
          </main>
          <Footer />
        </AuthProvider>
      </body>
    </html>
  );
}