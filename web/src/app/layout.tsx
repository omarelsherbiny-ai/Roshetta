// web/src/app/layout.tsx (root layout: fonts, icons, viewport, pre-paint theme script)
import type { Metadata, Viewport } from "next";
import "./globals.css";
import { DEFAULT_LANGUAGE, directionOf } from "@/lib/languages";
import { THEME_INIT_SCRIPT } from "@/lib/themeScript";

export const metadata: Metadata = {
  title: "روشتة | Roshetta Pharmacy AI",
  description: "نظام إدارة الصيدلية بالذكاء الاصطناعي",
};

// Pinch zoom stays enabled (no maximum-scale / user-scalable=no): people with low vision need it.
// themeColor is the light value; the theme script in <head> swaps it when the dark theme is active.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#ecfef3",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang={DEFAULT_LANGUAGE} dir={directionOf(DEFAULT_LANGUAGE)} suppressHydrationWarning>
      <head>
        {/* Theme: sets the `dark` class on <html> before first paint (no flash). Must stay the first script. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
        {/* Google Fonts — Stitch design spec */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Noto+Sans:wght@400;500;700&family=Plus+Jakarta+Sans:wght@700;800&family=Tajawal:wght@400;500;700;800&display=swap"
          rel="stylesheet"
        />
        {/* Material Symbols Outlined icons */}
        <link
          href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200"
          rel="stylesheet"
        />
        <meta name="mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="default" />
      </head>
      <body className="bg-surface text-on-surface font-body-md text-body-md flex flex-col min-h-screen selection:bg-primary-fixed selection:text-on-primary-fixed">
        {children}
      </body>
    </html>
  );
}