import type { Metadata, Viewport } from 'next';
import './globals.css';
import { ToastProvider } from '@/components/common/Toast';

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 5,
};

export const metadata: Metadata = {
  title: 'MediKiosk - Clinical History-Taking & Patient Intake Platform',
  description: 'AI-powered clinical history-taking and patient intake platform for Indian hospitals and AYUSH institutions.',
  keywords: ['healthcare', 'clinical intake', 'AI hospital kiosk', 'ABDM', 'FHIR', 'OPD automation', 'India healthcare', 'AYUSH'],
  authors: [{ name: 'MediKiosk Technologies' }],
  icons: {
    icon: '/favicon.ico',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,100..1000;1,9..40,100..1000&family=Playfair+Display:ital,wght@0,400..900;1,400..900&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="bg-white text-neutral-900 font-sans antialiased min-h-screen" suppressHydrationWarning>
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}
