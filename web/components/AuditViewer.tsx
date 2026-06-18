"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Mermaid } from "./Mermaid";
import { Terminal, Copy, FileText, Info, Search } from "lucide-react";
import { useEffect, useState } from "react";

// Sub-component for code highlighting to handle dynamic loading
function CodeBlock({ language, value }: { language: string; value: string }) {
  const [Highlighter, setHighlighter] = useState<any>(null);
  const [theme, setTheme] = useState<any>(null);

  useEffect(() => {
    import("react-syntax-highlighter").then((mod) => {
      setHighlighter(() => mod.Prism);
    });
    import("react-syntax-highlighter/dist/esm/styles/prism").then((mod) => {
      setTheme(() => mod.oneDark);
    });
  }, []);

  if (!Highlighter || !theme) {
    return (
      <pre className="bg-slate-900 p-6 rounded-b-2xl border-slate-700/50 overflow-x-auto">
        <code className="text-slate-300 text-[13px]">{value}</code>
      </pre>
    );
  }

  return (
    <Highlighter
      style={theme}
      language={language || "text"}
      PreTag="div"
      className="!m-0 !rounded-t-none !rounded-b-2xl !bg-slate-900/90 !border-slate-700/50 !p-6 shadow-2xl"
    >
      {value}
    </Highlighter>
  );
}

interface Props {
  markdown: string | null;
  loading?: boolean;
}

export function AuditViewer({ markdown, loading }: Props) {
  const [copied, setCopied] = useState(false);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-4 text-slate-500 text-sm">
        <div className="relative w-12 h-12">
          <div className="absolute inset-0 border-2 border-blue-500/20 rounded-full" />
          <div className="absolute inset-0 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        </div>
        <p className="animate-pulse font-medium tracking-tight">Generating consolidated audit…</p>
      </div>
    );
  }
  if (!markdown) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-slate-500 text-xs italic">
        <FileText className="w-8 h-8 opacity-20 mb-3" />
        No report content available yet.
      </div>
    );
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(markdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const hasConflict = markdown.includes("⚠ CONFLICT") || markdown.includes("⚠ CONFLIT");
  const isPartial = markdown.includes("PARTIAL AUDIT") || markdown.includes("AUDIT PARTIEL");

  return (
    <div className="space-y-10 animate-in fade-in slide-in-from-bottom-4 duration-700">
      {/* Report Controls */}
      <div className="flex items-center justify-end border-b border-slate-800 pb-6 mb-6">
        <button 
          onClick={handleCopy}
          className="inline-flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-bold rounded-xl transition-all active:scale-95 shadow-lg border border-slate-700/50"
        >
          {copied ? "Copied!" : "Copy Full Markdown"}
          <Copy className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="space-y-6">
        {hasConflict && (
          <div className="p-6 bg-red-500/5 border border-red-500/20 rounded-[2rem] text-sm text-red-400 flex items-start gap-4 shadow-xl backdrop-blur-sm">
            <div className="p-2 bg-red-500/20 rounded-xl mt-0.5">
              <Info className="w-4 h-4" />
            </div>
            <div>
              <p className="font-black uppercase tracking-widest text-[11px] mb-1">Conflict Detected</p>
              <p className="opacity-90 leading-relaxed font-medium">Contradictory evidence found between expert agents. Human verification is strictly required for the final diagnosis.</p>
            </div>
          </div>
        )}
        {isPartial && (
          <div className="p-6 bg-amber-500/5 border border-amber-500/20 rounded-[2rem] text-sm text-amber-400 flex items-start gap-4 shadow-xl backdrop-blur-sm">
            <div className="p-2 bg-amber-500/20 rounded-xl mt-0.5">
              <Search className="w-4 h-4" />
            </div>
            <div>
              <p className="font-black uppercase tracking-widest text-[11px] mb-1">Partial Analysis</p>
              <p className="opacity-90 leading-relaxed font-medium">One or more specialist agents failed to respond. The evidence matrix may be missing critical signals.</p>
            </div>
          </div>
        )}
      </div>

      <div className="prose-audit max-w-none text-slate-300 selection:bg-blue-500/30">

        <ReactMarkdown 
          remarkPlugins={[remarkGfm]}
          components={{
            // Important: Override pre to avoid double-nesting with our custom block UI
            pre: ({ children }) => <>{children}</>,
            code({ node, className, children, ...props }: any) {
              const match = /language-(\w+)/.exec(className || "");
              const language = match ? match[1] : "";
              const content = String(children).replace(/\n$/, "");

              // In react-markdown v9, we determine if it's a block by checking 
              // for a language class OR if it contains multiple lines.
              const isBlock = !!className || content.includes("\n");

              if (isBlock && language === "mermaid") {
                return <Mermaid chart={content} />;
              }

              if (!isBlock) {
                return (
                  <code className="bg-blue-500/10 text-blue-300 px-1.5 py-0.5 rounded-md border border-blue-500/20 text-[11px] font-mono font-bold" {...props}>
                    {children}
                  </code>
                );
              }

              return (
                <div className="relative group my-8">
                  <div className="flex items-center justify-between px-5 py-2 bg-slate-800/80 border-x border-t border-slate-700/50 rounded-t-2xl shadow-sm">
                    <div className="flex items-center gap-2">
                       <Terminal className="w-3.5 h-3.5 text-slate-500" />
                       <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">
                         {language || "snippet"}
                       </span>
                    </div>
                    <button className="text-slate-500 hover:text-white transition-colors">
                      <Copy className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <CodeBlock language={language} value={content} />
                </div>
              );
            },
          }}
        >
          {markdown}
        </ReactMarkdown>
      </div>

    </div>
  );
}
