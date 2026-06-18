"use client";

import { useEffect } from "react";

export default function MarcelProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    // Dynamically import @marcel/web-components purely on the client-side (browser)
    // to bypass SSR compilation and execution on the Node.js server.
    import("@marcel/web-components").then((module) => {
      module.defineCustomElements();
    }).catch((err) => {
      console.error("Failed to load @marcel/web-components dynamically:", err);
    });
  }, []);

  return <>{children}</>;
}
