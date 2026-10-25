import type { Metadata } from 'next';
import Nav from '@/components/Nav';
import { AuthProvider } from '@/lib/auth';
import './globals.css';

export const metadata: Metadata = {
  title: 'TCancy',
  description: 'Jobs and internships for HMTC ITS alumni',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-white text-gray-900">
        <AuthProvider>
          <Nav />
          <main className="mx-auto max-w-4xl p-6">{children}</main>
        </AuthProvider>
      </body>
    </html>
  );
}
