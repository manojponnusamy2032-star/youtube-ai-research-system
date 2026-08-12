import '../styles/globals.css';
import { ReactNode } from 'react';
import Providers from '../providers/ReactQueryProvider';
import ThemeProvider from '../providers/ThemeProvider';
import TopNav from '../components/ui/TopNav';
import Sidebar from '../components/ui/Sidebar';

export const metadata = {
  title: 'YAIRS Dashboard',
  description: 'YouTube AI Research System Dashboard',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <ThemeProvider>
            <div className="flex min-h-screen">
              <Sidebar />
              <div className="flex-1">
                <TopNav />
                <main className="p-6">{children}</main>
              </div>
            </div>
          </ThemeProvider>
        </Providers>
      </body>
    </html>
  );
}
