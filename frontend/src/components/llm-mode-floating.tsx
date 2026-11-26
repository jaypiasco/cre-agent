"use client";

import React, { useEffect, useRef, useState } from "react";
import { Eye, EyeOff, KeyRound, Sparkles, Trash2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { LlmClientConfig, LlmMode } from "@/lib/types";

interface LlmModeFloatingProps {
  config: LlmClientConfig;
  serverProvider: LlmMode | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onChange: (next: LlmClientConfig) => void;
}

const BYOK_PROVIDERS: { value: Exclude<LlmMode, "mock">; label: string; placeholder: string }[] = [
  { value: "gemini", label: "Google Gemini", placeholder: "AIza..." },
  { value: "openai", label: "OpenAI", placeholder: "sk-..." },
  { value: "anthropic", label: "Anthropic", placeholder: "sk-ant-..." },
];

const PROVIDER_SHORT_LABEL: Record<LlmMode, string> = {
  mock: "Mock Demo",
  gemini: "BYOK · Gemini",
  openai: "BYOK · OpenAI",
  anthropic: "BYOK · Anthropic",
};

export function LlmModeFloating({
  config,
  serverProvider,
  open,
  onOpenChange,
  onChange,
}: LlmModeFloatingProps) {
  const [showKey, setShowKey] = useState(false);
  const [lastByokProvider, setLastByokProvider] =
    useState<Exclude<LlmMode, "mock">>("gemini");
  const containerRef = useRef<HTMLDivElement>(null);

  const isMock = config.mode === "mock";
  const hasKey = config.apiKey.trim().length > 0;
  const currentByokProvider: Exclude<LlmMode, "mock"> =
    config.mode === "mock" ? lastByokProvider : config.mode;

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onOpenChange(false);
    };
    const handleClickOutside = (e: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        onOpenChange(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [open, onOpenChange]);

  const statusDotClass = isMock
    ? "bg-amber-500"
    : hasKey
      ? "bg-emerald-500"
      : "bg-rose-500";

  const activeProviderMeta =
    BYOK_PROVIDERS.find((p) => p.value === currentByokProvider) ??
    BYOK_PROVIDERS[0];

  return (
    <div
      ref={containerRef}
      className="fixed bottom-5 right-5 z-40 flex flex-col items-end gap-2.5"
    >
      {open && (
        <div
          role="dialog"
          aria-label="LLM Provider & API Key Settings"
          className="w-80 rounded-[10px] border border-slate-200 bg-white p-4 shadow-lg shadow-slate-900/10"
        >
          <div className="mb-3 flex items-start justify-between gap-2">
            <div>
              <h2 className="text-sm font-semibold text-slate-900">
                Inference Mode
              </h2>
              <p className="text-[11px] text-slate-500">
                Server default:{" "}
                <span className="font-mono font-medium text-slate-700">
                  {serverProvider ?? "unknown"}
                </span>
              </p>
            </div>
            <button
              type="button"
              onClick={() => onOpenChange(false)}
              aria-label="Close inference settings"
              className="rounded-md p-1 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Mode Toggle */}
          <div className="grid grid-cols-2 gap-1 rounded-lg border border-slate-200 bg-slate-50 p-1">
            <button
              type="button"
              onClick={() => onChange({ ...config, mode: "mock" })}
              className={`flex items-center justify-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors ${
                isMock
                  ? "bg-white text-slate-900 shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <Sparkles className="h-3.5 w-3.5 text-amber-600" />
              Mock Demo
            </button>
            <button
              type="button"
              onClick={() =>
                onChange({ ...config, mode: currentByokProvider })
              }
              className={`flex items-center justify-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors ${
                !isMock
                  ? "bg-white text-slate-900 shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <KeyRound className="h-3.5 w-3.5 text-emerald-600" />
              Bring Key
            </button>
          </div>

          {isMock ? (
            <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50/70 px-3 py-2 text-xs leading-relaxed text-amber-900">
              Key-free deterministic mode. Ideal for testing the 4 built-in
              sample PDFs, math gates, and Yardi export live.
            </p>
          ) : (
            <div className="mt-3 space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="byok-provider" className="text-xs font-medium">
                  Provider
                </Label>
                <Select
                  value={currentByokProvider}
                  onValueChange={(val) => {
                    const nextProvider = val as Exclude<LlmMode, "mock">;
                    setLastByokProvider(nextProvider);
                    onChange({ ...config, mode: nextProvider });
                  }}
                >
                  <SelectTrigger id="byok-provider" className="h-9 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {BYOK_PROVIDERS.map((p) => (
                      <SelectItem key={p.value} value={p.value} className="text-xs">
                        {p.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <Label htmlFor="byok-api-key" className="text-xs font-medium">
                    API Key
                  </Label>
                  {hasKey && (
                    <button
                      type="button"
                      onClick={() => onChange({ ...config, apiKey: "" })}
                      className="inline-flex items-center gap-1 text-[11px] text-slate-500 hover:text-rose-600"
                    >
                      <Trash2 className="h-3 w-3" />
                      Clear
                    </button>
                  )}
                </div>
                <div className="relative">
                  <Input
                    id="byok-api-key"
                    type={showKey ? "text" : "password"}
                    value={config.apiKey}
                    onChange={(e) =>
                      onChange({ ...config, apiKey: e.target.value })
                    }
                    placeholder={activeProviderMeta.placeholder}
                    autoComplete="off"
                    spellCheck={false}
                    className="h-9 pr-9 font-mono text-xs"
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey((prev) => !prev)}
                    aria-label={showKey ? "Hide API key" : "Show API key"}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700"
                  >
                    {showKey ? (
                      <EyeOff className="h-3.5 w-3.5" />
                    ) : (
                      <Eye className="h-3.5 w-3.5" />
                    )}
                  </button>
                </div>
                <p className="text-[11px] leading-snug text-slate-500">
                  Kept in browser <code className="font-mono">sessionStorage</code>{" "}
                  and sent per-request only; never stored on the server.
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Floating Trigger Pill */}
      <Button
        type="button"
        onClick={() => onOpenChange(!open)}
        aria-expanded={open}
        className="h-10 gap-2 rounded-full border border-slate-200 bg-white px-4 text-xs font-medium text-slate-900 shadow-md shadow-slate-900/10 hover:bg-slate-50"
      >
        <span className={`h-2 w-2 rounded-full ${statusDotClass}`} />
        {isMock ? (
          <Sparkles className="h-3.5 w-3.5 text-amber-600" />
        ) : (
          <KeyRound className="h-3.5 w-3.5 text-emerald-600" />
        )}
        <span>{PROVIDER_SHORT_LABEL[config.mode]}</span>
      </Button>
    </div>
  );
}
