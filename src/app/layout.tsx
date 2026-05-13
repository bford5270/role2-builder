import type { Metadata } from "next";
import { Roboto_Slab, IBM_Plex_Sans, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";

const robotoSlab = Roboto_Slab({
  variable: "--font-display",
  subsets: ["latin"],
  weight: ["400", "500", "700"],
  display: "swap",
});

const ibmPlexSans = IBM_Plex_Sans({
  variable: "--font-body",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
});

const ibmPlexMono = IBM_Plex_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Role 2 Builder",
  description: "Scenario builder for USMC Role 2 medical training exercises.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" data-theme="console">
      <body
        className={`${robotoSlab.variable} ${ibmPlexSans.variable} ${ibmPlexMono.variable} antialiased`}
      >
        <div className="classification-banner">Unclassified // FOUO</div>
        {children}
      </body>
    </html>
  );
}
