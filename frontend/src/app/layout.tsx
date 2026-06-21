import type { Metadata } from "next";
import Script from "next/script";
import "./globals.css";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Menas HR Chatbot",
  description: "AI Chat Application",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const runtimeConfig = {
    backendUrl:
      process.env.NEXT_PUBLIC_BACKEND_URL ??
      process.env.BACKEND_URL ??
      "/api",
  };

  return (
    <html lang="en">
      <body className="antialiased h-screen overflow-hidden bg-white">
        <Script
          id="runtime-config"
          strategy="beforeInteractive"
          dangerouslySetInnerHTML={{
            __html: `window.__APP_RUNTIME_CONFIG__ = ${JSON.stringify(runtimeConfig)};`,
          }}
        />
        {children}
      </body>
    </html>
  );
}
