import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import "../styles/sbp-tokens.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "MetricMind",
  description: "AI-supported DevOps decision intelligence",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="font-sans bg-slate-50 text-slate-900 min-h-screen">
        {children}
      </body>
    </html>
  );
}
