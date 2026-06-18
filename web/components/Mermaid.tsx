"use client";

import { useEffect, useRef, useState } from "react";

export function Mermaid({ chart }: { chart: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [isLoaded, setIsLoaded] = useState(false);

  useEffect(() => {
    const renderDiagram = async () => {
      try {
        // Dynamically import mermaid only on the client
        const { default: mermaid } = await import("mermaid");
        
        mermaid.initialize({
          startOnLoad: false, // Changed to false as we manual render
          theme: "dark",
          securityLevel: "loose",
          fontFamily: "var(--font-sans)",
        });

        if (ref.current) {
          // Generate a unique ID for this diagram
          const id = `mermaid-${Math.random().toString(36).substr(2, 9)}`;
          const { svg } = await mermaid.render(id, chart);
          if (ref.current) {
            ref.current.innerHTML = svg;
            setIsLoaded(true);
          }
        }
      } catch (error) {
        console.error("Mermaid rendering error:", error);
        if (ref.current) {
          ref.current.innerHTML = `<pre class="text-red-500 text-[10px] bg-red-500/10 p-4 rounded-xl border border-red-500/20">${error}</pre>`;
        }
      }
    };

    renderDiagram();
  }, [chart]);

  return (
    <div className="flex justify-center my-8 bg-slate-900/30 p-8 rounded-3xl border border-slate-800/50 shadow-inner overflow-x-auto min-h-[100px] transition-opacity duration-500">
      {!isLoaded && (
        <div className="flex items-center gap-2 text-slate-500 text-[10px] font-bold uppercase tracking-widest animate-pulse">
           <div className="w-1.5 h-1.5 rounded-full bg-blue-500" />
           Rendering Diagram...
        </div>
      )}
      <div ref={ref} className={clsx("mermaid", !isLoaded && "hidden")} />
    </div>
  );
}

function clsx(...classes: any[]) {
  return classes.filter(Boolean).join(" ");
}
