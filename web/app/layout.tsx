import type { Metadata } from "next";
import "@marcel/web-tokens/dist/index.css";
import "./globals.css";
import { Providers } from "./providers";
import { SideBar } from "@/components/SideBar";
import MarcelProvider from "./marcel-provider";
import { OpsStrip } from "@/components/OpsStrip";
import { AttentionCard } from "@/components/AttentionCard";

export const metadata: Metadata = {
  title: "Kafka Agentic Platform",
  description: "Incident auto-triage OS for Kafka InfraOps",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark" data-mode="dark">
      <body className="min-h-screen flex bg-slate-950">
        <Providers>
          <MarcelProvider>
            <SideBar />
            <main className="flex-1 flex flex-col min-w-0 h-screen overflow-y-auto">
              <OpsStrip />
              <AttentionCard />
              <div className="p-8 max-w-[1600px] w-full mx-auto">
                {children}
              </div>
            </main>
          </MarcelProvider>
        </Providers>
      </body>
    </html>
  );
}
