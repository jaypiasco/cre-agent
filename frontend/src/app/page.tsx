"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  Copy,
  Download,
  Eye,
  FileCheck2,
  FileSpreadsheet,
  FileText,
  Loader2,
  ShieldCheck,
  Sparkles,
  Upload,
} from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  analyzeInvoicePdf,
  exportYardiInvoice,
  fetchChartOfAccounts,
  fetchHealth,
} from "@/lib/api";
import type {
  ChartOfAccountsEntry,
  InvoiceAnalysisResponse,
  YardiExportResponse,
} from "@/lib/types";

interface SamplePreset {
  id: string;
  label: string;
  tag: string;
  filename: string;
  path: string;
}

interface QueuedInvoice {
  id: string;
  filename: string;
  status: "pending" | "analyzing" | "valid" | "needs_review" | "exported" | "error";
  analysis?: InvoiceAnalysisResponse;
  error?: string;
}

const SAMPLE_PRESETS: SamplePreset[] = [
  {
    id: "hvac",
    label: "HVAC · Apex",
    tag: "Text · Valid",
    filename: "hvac_apex_inv_88412.pdf",
    path: "/samples/hvac_apex_inv_88412.pdf",
  },
  {
    id: "roofing",
    label: "Roofing · Summit",
    tag: "Text · Valid",
    filename: "roofing_summit_scr_4419.pdf",
    path: "/samples/roofing_summit_scr_4419.pdf",
  },
  {
    id: "scanned",
    label: "Scanned · GreenView",
    tag: "Vision · Review",
    filename: "landscaping_greenview_scanned.pdf",
    path: "/samples/landscaping_greenview_scanned.pdf",
  },
  {
    id: "math-error",
    label: "Math Error · Metro Utility",
    tag: "Mismatch · Review",
    filename: "utility_math_error_sample.pdf",
    path: "/samples/utility_math_error_sample.pdf",
  },
];

const FALLBACK_COA: ChartOfAccountsEntry[] = [
  { gl_code: "5100", account_name: "Property Taxes", examples: "County tax, assessments" },
  { gl_code: "5200", account_name: "Property Insurance", examples: "Liability, hazard" },
  { gl_code: "6100", account_name: "HVAC & Mechanical R&M", examples: "Chiller, RTU, refrigerant" },
  { gl_code: "6200", account_name: "Roofing & Building Envelope", examples: "Membrane, flashing" },
  { gl_code: "6300", account_name: "Landscaping & Grounds", examples: "Lawn, irrigation, snow" },
  { gl_code: "6400", account_name: "Janitorial & Waste", examples: "Cleaning, dumpster" },
  { gl_code: "6500", account_name: "Utilities (Water/Electric/Gas)", examples: "Municipal water, power" },
  { gl_code: "6600", account_name: "Security & Life Safety", examples: "Fire alarm, sprinkler" },
  { gl_code: "7100", account_name: "Legal & Professional Fees", examples: "Lease review, CPA" },
];

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(value);
}

function defaultBatchId(): string {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `BATCH-${y}${m}${d}-001`;
}

function triggerDownload(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export default function CreWorkbenchPage() {
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);
  const [langfuseEnabled, setLangfuseEnabled] = useState<boolean>(false);
  const [coa, setCoa] = useState<ChartOfAccountsEntry[]>(FALLBACK_COA);

  const [activeFilename, setActiveFilename] = useState<string>("");
  const [isAnalyzing, setIsAnalyzing] = useState<boolean>(false);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [analysis, setAnalysis] = useState<InvoiceAnalysisResponse | null>(null);
  const [queue, setQueue] = useState<QueuedInvoice[]>([]);
  const [activeQueueId, setActiveQueueId] = useState<string | null>(null);
  const [selectedGlCode, setSelectedGlCode] = useState<string>("");
  const [humanApproved, setHumanApproved] = useState<boolean>(false);
  const [batchId, setBatchId] = useState<string>("BATCH-001");
  const [approvedBy, setApprovedBy] = useState<string>("ap_reviewer");

  const [isExporting, setIsExporting] = useState<boolean>(false);
  const [exportResult, setExportResult] = useState<YardiExportResponse | null>(null);
  const [copiedTrace, setCopiedTrace] = useState<boolean>(false);

  useEffect(() => {
    let mounted = true;
    fetchHealth()
      .then((h) => {
        if (!mounted) return;
        setApiOnline(h.status === "ok");
        setLangfuseEnabled(Boolean(h.langfuse_enabled));
      })
      .catch(() => {
        if (!mounted) return;
        setApiOnline(false);
      });

    fetchChartOfAccounts()
      .then((entries) => {
        if (mounted && entries.length > 0) {
          setCoa(entries);
        }
      })
      .catch(() => {
        // Keep fallback Chart of Accounts when API is offline
      });

    return () => {
      mounted = false;
    };
  }, []);

  const selectQueuedInvoice = useCallback((item: QueuedInvoice) => {
    setActiveQueueId(item.id);
    setActiveFilename(item.filename);
    setExportResult(null);
    setHumanApproved(false);
    setErrorMsg(item.error ?? null);
    if (item.analysis) {
      setAnalysis(item.analysis);
      setSelectedGlCode(item.analysis.gl_recommendation.gl_code);
    } else {
      setAnalysis(null);
    }
  }, []);

  const runBatchAnalysis = useCallback(async (files: File[]) => {
    if (files.length === 0) return;
    setErrorMsg(null);
    setExportResult(null);
    setHumanApproved(false);
    setBatchId(defaultBatchId());
    setIsAnalyzing(true);

    const newEntries: QueuedInvoice[] = files.map((file, idx) => ({
      id: `${Date.now()}-${idx}-${file.name}`,
      filename: file.name,
      status: "pending",
    }));
    setQueue((prev) => [...newEntries, ...prev]);

    for (let i = 0; i < files.length; i += 1) {
      const file = files[i];
      const entryId = newEntries[i].id;
      setActiveFilename(file.name);
      setActiveQueueId(entryId);
      setQueue((prev) =>
        prev.map((q) => (q.id === entryId ? { ...q, status: "analyzing" } : q))
      );

      try {
        const result = await analyzeInvoicePdf(file);
        const nextStatus =
          result.validation.status === "VALID" ? "valid" : "needs_review";
        setQueue((prev) =>
          prev.map((q) =>
            q.id === entryId ? { ...q, status: nextStatus, analysis: result } : q
          )
        );
        if (i === 0 || files.length === 1) {
          setAnalysis(result);
          setSelectedGlCode(result.gl_recommendation.gl_code);
        }
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Failed to analyze invoice PDF.";
        setQueue((prev) =>
          prev.map((q) =>
            q.id === entryId ? { ...q, status: "error", error: message } : q
          )
        );
        if (i === 0 || files.length === 1) {
          setErrorMsg(message);
          setAnalysis(null);
        }
      }
    }

    setIsAnalyzing(false);
  }, []);

  const runAnalysis = useCallback(
    async (file: File) => {
      await runBatchAnalysis([file]);
    },
    [runBatchAnalysis]
  );

  const handleSampleClick = async (preset: SamplePreset) => {
    setErrorMsg(null);
    setIsAnalyzing(true);
    setActiveFilename(preset.filename);
    try {
      const res = await fetch(preset.path);
      if (!res.ok) {
        throw new Error(`Could not load sample PDF (${preset.filename}).`);
      }
      const blob = await res.blob();
      const file = new File([blob], preset.filename, { type: "application/pdf" });
      await runAnalysis(file);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to load sample PDF.";
      setErrorMsg(message);
      setIsAnalyzing(false);
    }
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []).filter((f) =>
      f.name.toLowerCase().endsWith(".pdf")
    );
    if (files.length > 0) {
      void runBatchAnalysis(files);
    }
    e.target.value = "";
  };

  const handleDrop = (e: React.DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    setIsDragging(false);
    const dropped = Array.from(e.dataTransfer.files ?? []);
    if (dropped.length === 0) return;
    const pdfs = dropped.filter((f) => f.name.toLowerCase().endsWith(".pdf"));
    if (pdfs.length === 0) {
      setErrorMsg("Only .pdf invoice files are supported.");
      return;
    }
    void runBatchAnalysis(pdfs);
  };

  const selectedGlEntry = useMemo(() => {
    return (
      coa.find((entry) => entry.gl_code === selectedGlCode) ?? {
        gl_code: selectedGlCode,
        account_name: analysis?.gl_recommendation.gl_account_name ?? "",
        examples: "",
      }
    );
  }, [coa, selectedGlCode, analysis]);

  const handleExport = async (downloadType: "csv" | "json") => {
    if (!analysis || !humanApproved) return;
    setErrorMsg(null);
    setIsExporting(true);

    try {
      const res = await exportYardiInvoice({
        batch_id: batchId.trim() || defaultBatchId(),
        vendor_name: analysis.invoice.vendor_name,
        invoice_number: analysis.invoice.invoice_number,
        invoice_date: analysis.invoice.invoice_date,
        property_address: analysis.invoice.property_address,
        gl_code: selectedGlEntry.gl_code,
        gl_account_name: selectedGlEntry.account_name,
        amount_due: analysis.invoice.amount_due,
        human_approved: humanApproved,
        approved_by: approvedBy.trim() || "ap_reviewer",
        langfuse_trace_id: analysis.trace_id,
      });

      setExportResult(res);
      if (activeQueueId) {
        setQueue((prev) =>
          prev.map((q) => (q.id === activeQueueId ? { ...q, status: "exported" } : q))
        );
      }

      if (downloadType === "csv") {
        triggerDownload(res.csv_content, res.filename, "text/csv;charset=utf-8");
      } else {
        const jsonFilename = res.filename.replace(/\.csv$/i, ".json");
        triggerDownload(
          JSON.stringify(res.json_payload, null, 2),
          jsonFilename,
          "application/json"
        );
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Export failed.";
      setErrorMsg(message);
    } finally {
      setIsExporting(false);
    }
  };

  const handleCopyTrace = async () => {
    if (!analysis?.trace_id) return;
    await navigator.clipboard.writeText(analysis.trace_id);
    setCopiedTrace(true);
    setTimeout(() => setCopiedTrace(false), 1800);
  };

  const isValid = analysis?.validation.status === "VALID";

  return (
    <div className="min-h-screen bg-slate-50/70 text-slate-900">
      {/* Top Navigation Bar */}
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-3.5 sm:px-6">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-900 text-white">
              <Building2 className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-base font-semibold tracking-tight text-slate-900">
                CRE-Agent
              </h1>
              <p className="text-xs text-slate-500">
                Commercial Real Estate AP &amp; GL Coding Workbench
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            <Badge
              variant="outline"
              className={
                apiOnline
                  ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                  : apiOnline === false
                    ? "border-rose-200 bg-rose-50 text-rose-700"
                    : "border-slate-200 bg-slate-50 text-slate-600"
              }
            >
              <span
                className={`mr-1.5 h-1.5 w-1.5 rounded-full ${
                  apiOnline
                    ? "bg-emerald-500"
                    : apiOnline === false
                      ? "bg-rose-500"
                      : "bg-slate-400"
                }`}
              />
              {apiOnline
                ? "API Connected"
                : apiOnline === false
                  ? "API Offline"
                  : "Checking API..."}
            </Badge>
            {langfuseEnabled && (
              <Badge
                variant="outline"
                className="border-sky-200 bg-sky-50 text-sky-700"
              >
                Langfuse Tracing On
              </Badge>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6">
        {/* Ingestion & Sample Quick-Load Bar */}
        <Card className="border-slate-200 bg-white shadow-xs">
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-semibold">
              Invoice Ingestion
            </CardTitle>
            <CardDescription>
              Load a sample CRE vendor invoice or upload your own PDF to run
              multimodal extraction, deterministic Decimal math gates, and GL
              coding.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="mr-1 text-xs font-medium uppercase tracking-wider text-slate-500">
                Quick-Load Samples:
              </span>
              {SAMPLE_PRESETS.map((preset) => (
                <Button
                  key={preset.id}
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={isAnalyzing}
                  onClick={() => void handleSampleClick(preset)}
                  className="h-8 gap-2 border-slate-200 bg-white text-xs font-medium hover:bg-slate-100"
                >
                  <FileText className="h-3.5 w-3.5 text-slate-500" />
                  <span>{preset.label}</span>
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600">
                    {preset.tag}
                  </span>
                </Button>
              ))}
            </div>

            <label
              htmlFor="pdf-upload"
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-6 text-center transition-colors ${
                isDragging
                  ? "border-slate-900 bg-slate-100/80"
                  : "border-slate-200 bg-slate-50/50 hover:border-slate-300 hover:bg-slate-50"
              }`}
            >
              <input
                id="pdf-upload"
                type="file"
                accept=".pdf,application/pdf"
                multiple
                className="sr-only"
                onChange={handleFileInput}
                disabled={isAnalyzing}
              />
              {isAnalyzing ? (
                <div className="flex items-center gap-2.5 text-sm font-medium text-slate-700">
                  <Loader2 className="h-5 w-5 animate-spin text-slate-900" />
                  <span>Analyzing {activeFilename || "invoice"}...</span>
                </div>
              ) : (
                <>
                  <Upload className="mb-2 h-5 w-5 text-slate-500" />
                  <p className="text-sm font-medium text-slate-700">
                    Drop one or more vendor invoice PDFs here, or{" "}
                    <span className="underline underline-offset-4">browse</span>
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    Supports batch upload of text-based &amp; scanned PDFs (up to
                    5 pages each)
                  </p>
                </>
              )}
            </label>

            {queue.length > 0 && (
              <div className="space-y-2 pt-1">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium uppercase tracking-wider text-slate-500">
                    Invoice Queue ({queue.length})
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={isAnalyzing}
                    onClick={() => {
                      setQueue([]);
                      setActiveQueueId(null);
                    }}
                    className="h-6 px-2 text-xs text-slate-500 hover:text-slate-800"
                  >
                    Clear
                  </Button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {queue.map((item) => {
                    const isActive = item.id === activeQueueId;
                    const badgeClass =
                      item.status === "valid" || item.status === "exported"
                        ? "bg-emerald-100 text-emerald-800"
                        : item.status === "needs_review"
                          ? "bg-amber-100 text-amber-800"
                          : item.status === "error"
                            ? "bg-rose-100 text-rose-800"
                            : "bg-slate-100 text-slate-600";
                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => selectQueuedInvoice(item)}
                        className={`flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs transition-colors ${
                          isActive
                            ? "border-slate-900 bg-slate-900 text-white"
                            : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                        }`}
                      >
                        <span className="max-w-[180px] truncate font-medium">
                          {item.filename}
                        </span>
                        <span
                          className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                            isActive ? "bg-white/20 text-white" : badgeClass
                          }`}
                        >
                          {item.status.replace("_", " ")}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {errorMsg && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Processing Error</AlertTitle>
            <AlertDescription>{errorMsg}</AlertDescription>
          </Alert>
        )}

        {!analysis && !isAnalyzing && (
          <div className="rounded-lg border border-slate-200 bg-white px-6 py-12 text-center">
            <FileCheck2 className="mx-auto mb-3 h-8 w-8 text-slate-400" />
            <h2 className="text-sm font-semibold text-slate-900">
              No invoice loaded yet
            </h2>
            <p className="mx-auto mt-1 max-w-md text-xs text-slate-500">
              Select one of the 4 CRE sample invoices above or upload a PDF to
              inspect extracted line items, deterministic math verification, and
              HITL-gated Yardi export.
            </p>
          </div>
        )}

        {analysis && (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
            {/* Left Column: Extraction & Deterministic Math Gate */}
            <div className="space-y-6 lg:col-span-7">
              <Card className="border-slate-200 bg-white shadow-xs">
                <CardHeader className="pb-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <CardTitle className="text-base font-semibold">
                        Extraction &amp; Validation Gate
                      </CardTitle>
                      <CardDescription className="mt-0.5">
                        {activeFilename}
                      </CardDescription>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      {isValid ? (
                        <Badge className="gap-1 bg-emerald-600 text-white hover:bg-emerald-600">
                          <CheckCircle2 className="h-3.5 w-3.5" />
                          Math Verified
                        </Badge>
                      ) : (
                        <Badge className="gap-1 bg-amber-500 text-white hover:bg-amber-500">
                          <AlertTriangle className="h-3.5 w-3.5" />
                          Needs Review
                        </Badge>
                      )}

                      <Badge
                        variant="outline"
                        className="gap-1 border-slate-200 bg-slate-50 font-mono text-[11px] uppercase text-slate-700"
                      >
                        {analysis.extraction_mode === "vision" ? (
                          <Eye className="h-3 w-3" />
                        ) : (
                          <FileText className="h-3 w-3" />
                        )}
                        {analysis.extraction_mode}
                      </Badge>

                      <Badge
                        variant="outline"
                        className="border-slate-200 bg-slate-50 font-mono text-[11px] text-slate-700"
                      >
                        Conf:{" "}
                        {Math.round(
                          analysis.invoice.extraction_confidence * 100
                        )}
                        %
                      </Badge>
                    </div>
                  </div>

                  {analysis.trace_id && (
                    <div className="mt-3 flex items-center gap-2 text-xs text-slate-500">
                      <span>Trace ID:</span>
                      <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-700">
                        {analysis.trace_id}
                      </code>
                      <button
                        type="button"
                        onClick={() => void handleCopyTrace()}
                        className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-slate-500 hover:bg-slate-100 hover:text-slate-900"
                        title="Copy Trace ID"
                      >
                        <Copy className="h-3 w-3" />
                        {copiedTrace ? "Copied" : "Copy"}
                      </button>
                    </div>
                  )}
                </CardHeader>

                <CardContent className="space-y-5">
                  {analysis.validation.warnings.length > 0 && (
                    <Alert className="border-amber-200 bg-amber-50 text-amber-900">
                      <AlertTriangle className="h-4 w-4 text-amber-600" />
                      <AlertTitle className="text-sm font-semibold">
                        Deterministic Gate Flagged Issues
                      </AlertTitle>
                      <AlertDescription>
                        <ul className="mt-1 list-disc space-y-1 pl-4 text-xs">
                          {analysis.validation.warnings.map((w, idx) => (
                            <li key={idx}>{w}</li>
                          ))}
                        </ul>
                      </AlertDescription>
                    </Alert>
                  )}

                  {/* Invoice Header Metadata */}
                  <div className="grid grid-cols-1 gap-4 rounded-lg border border-slate-200 bg-slate-50/60 p-4 sm:grid-cols-2">
                    <div>
                      <p className="text-[11px] font-medium uppercase tracking-wider text-slate-500">
                        Vendor
                      </p>
                      <p className="mt-0.5 text-sm font-semibold text-slate-900">
                        {analysis.invoice.vendor_name}
                      </p>
                    </div>
                    <div>
                      <p className="text-[11px] font-medium uppercase tracking-wider text-slate-500">
                        Invoice Number
                      </p>
                      <p className="mt-0.5 font-mono text-sm font-semibold text-slate-900">
                        {analysis.invoice.invoice_number}
                      </p>
                    </div>
                    <div>
                      <p className="text-[11px] font-medium uppercase tracking-wider text-slate-500">
                        Invoice Date / Due Date
                      </p>
                      <p className="mt-0.5 text-sm text-slate-800">
                        {analysis.invoice.invoice_date}
                        {analysis.invoice.due_date
                          ? ` → ${analysis.invoice.due_date}`
                          : ""}
                      </p>
                    </div>
                    <div>
                      <p className="text-[11px] font-medium uppercase tracking-wider text-slate-500">
                        Service Property
                      </p>
                      <p className="mt-0.5 text-sm text-slate-800">
                        {analysis.invoice.property_address}
                      </p>
                    </div>
                  </div>

                  {/* Line Items Table */}
                  <div className="overflow-hidden rounded-lg border border-slate-200">
                    <Table>
                      <TableHeader className="bg-slate-50">
                        <TableRow>
                          <TableHead className="text-xs">Description</TableHead>
                          <TableHead className="text-right text-xs">
                            Qty
                          </TableHead>
                          <TableHead className="text-right text-xs">
                            Unit Price
                          </TableHead>
                          <TableHead className="text-right text-xs">
                            Line Total
                          </TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {analysis.invoice.line_items.map((item, idx) => (
                          <TableRow key={idx}>
                            <TableCell className="text-xs font-medium text-slate-800">
                              {item.description}
                            </TableCell>
                            <TableCell className="text-right font-mono text-xs text-slate-600">
                              {item.quantity}
                            </TableCell>
                            <TableCell className="text-right font-mono text-xs text-slate-600">
                              {formatCurrency(item.unit_price)}
                            </TableCell>
                            <TableCell className="text-right font-mono text-xs font-medium text-slate-900">
                              {formatCurrency(item.line_total)}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>

                  {/* Totals Summary */}
                  <div className="flex justify-end">
                    <dl className="w-full max-w-xs space-y-1.5 text-sm">
                      <div className="flex justify-between text-slate-600">
                        <dt>Subtotal</dt>
                        <dd className="font-mono">
                          {formatCurrency(analysis.invoice.subtotal)}
                        </dd>
                      </div>
                      <div className="flex justify-between text-slate-600">
                        <dt>Tax</dt>
                        <dd className="font-mono">
                          {formatCurrency(analysis.invoice.tax_amount)}
                        </dd>
                      </div>
                      {analysis.invoice.discount_amount > 0 && (
                        <div className="flex justify-between text-emerald-700">
                          <dt>Discount</dt>
                          <dd className="font-mono">
                            -{formatCurrency(analysis.invoice.discount_amount)}
                          </dd>
                        </div>
                      )}
                      <Separator className="my-1.5" />
                      <div className="flex justify-between text-base font-semibold text-slate-900">
                        <dt>Amount Due</dt>
                        <dd className="font-mono">
                          {formatCurrency(analysis.invoice.amount_due)}
                        </dd>
                      </div>
                    </dl>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Right Column: GL Coding & HITL Approval */}
            <div className="space-y-6 lg:col-span-5">
              <Card className="border-slate-200 bg-white shadow-xs">
                <CardHeader className="pb-4">
                  <CardTitle className="flex items-center gap-2 text-base font-semibold">
                    <Sparkles className="h-4 w-4 text-slate-700" />
                    GL Coding &amp; HITL Approval
                  </CardTitle>
                  <CardDescription>
                    Review the recommended Chart of Accounts code and toggle
                    Human Approval to unlock Yardi export.
                  </CardDescription>
                </CardHeader>

                <CardContent className="space-y-5">
                  {/* AI GL Recommendation */}
                  <div className="rounded-lg border border-slate-200 bg-slate-50/70 p-4">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[11px] font-medium uppercase tracking-wider text-slate-500">
                        Recommended GL Account
                      </span>
                      <Badge
                        variant="outline"
                        className="border-slate-200 bg-white font-mono text-[11px]"
                      >
                        {Math.round(
                          analysis.gl_recommendation.gl_confidence * 100
                        )}
                        % match
                      </Badge>
                    </div>
                    <p className="mt-1.5 text-sm font-semibold text-slate-900">
                      {analysis.gl_recommendation.gl_code} —{" "}
                      {analysis.gl_recommendation.gl_account_name}
                    </p>
                    <p className="mt-1.5 text-xs leading-relaxed text-slate-600">
                      {analysis.gl_recommendation.explanation}
                    </p>
                  </div>

                  {/* GL Account Override */}
                  <div className="space-y-2">
                    <Label htmlFor="gl-select" className="text-xs font-medium">
                      GL Account (Override if needed)
                    </Label>
                    <Select
                      value={selectedGlCode}
                      onValueChange={(value) => {
                        if (value) setSelectedGlCode(value);
                      }}
                    >
                      <SelectTrigger id="gl-select" className="w-full bg-white">
                        <SelectValue placeholder="Select GL Account" />
                      </SelectTrigger>
                      <SelectContent>
                        {coa.map((entry) => (
                          <SelectItem
                            key={entry.gl_code}
                            value={entry.gl_code}
                          >
                            {entry.gl_code} — {entry.account_name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  {/* Batch & Reviewer */}
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div className="space-y-1.5">
                      <Label htmlFor="batch-id" className="text-xs font-medium">
                        Yardi Batch ID
                      </Label>
                      <Input
                        id="batch-id"
                        value={batchId}
                        onChange={(e) => setBatchId(e.target.value)}
                        className="h-9 font-mono text-xs"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label
                        htmlFor="approved-by"
                        className="text-xs font-medium"
                      >
                        Reviewer
                      </Label>
                      <Input
                        id="approved-by"
                        value={approvedBy}
                        onChange={(e) => setApprovedBy(e.target.value)}
                        className="h-9 text-xs"
                      />
                    </div>
                  </div>

                  <Separator />

                  {/* Explicit HITL Gate Switch */}
                  <div
                    className={`flex items-center justify-between rounded-lg border p-3.5 transition-colors ${
                      humanApproved
                        ? "border-emerald-200 bg-emerald-50/70"
                        : "border-slate-200 bg-slate-50/70"
                    }`}
                  >
                    <div className="space-y-0.5 pr-3">
                      <Label
                        htmlFor="hitl-switch"
                        className="flex items-center gap-1.5 text-sm font-semibold text-slate-900"
                      >
                        <ShieldCheck
                          className={`h-4 w-4 ${
                            humanApproved
                              ? "text-emerald-600"
                              : "text-slate-400"
                          }`}
                        />
                        Human Approval:{" "}
                        {humanApproved ? "Approved" : "Pending"}
                      </Label>
                      <p className="text-xs text-slate-500">
                        Required before generating Yardi CSV or audit JSON.
                      </p>
                    </div>
                    <Switch
                      id="hitl-switch"
                      checked={humanApproved}
                      onCheckedChange={setHumanApproved}
                    />
                  </div>

                  {/* Export Buttons */}
                  <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                    <Button
                      type="button"
                      disabled={!humanApproved || isExporting}
                      onClick={() => void handleExport("csv")}
                      className="w-full gap-2"
                    >
                      {isExporting ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <FileSpreadsheet className="h-4 w-4" />
                      )}
                      Download Yardi CSV
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      disabled={!humanApproved || isExporting}
                      onClick={() => void handleExport("json")}
                      className="w-full gap-2"
                    >
                      <Download className="h-4 w-4" />
                      Download Audit JSON
                    </Button>
                  </div>

                  {/* Live Export Payload Preview */}
                  {exportResult && (
                    <div className="space-y-2 pt-1">
                      <p className="text-xs font-medium text-slate-700">
                        Generated Export Preview ({exportResult.filename})
                      </p>
                      <Tabs defaultValue="csv" className="w-full">
                        <TabsList className="grid w-full grid-cols-2">
                          <TabsTrigger value="csv" className="text-xs">
                            Yardi CSV
                          </TabsTrigger>
                          <TabsTrigger value="json" className="text-xs">
                            Audit JSON
                          </TabsTrigger>
                        </TabsList>
                        <TabsContent value="csv">
                          <pre className="max-h-48 overflow-auto rounded-md border border-slate-200 bg-slate-950 p-3 font-mono text-[11px] text-slate-100">
                            {exportResult.csv_content}
                          </pre>
                        </TabsContent>
                        <TabsContent value="json">
                          <pre className="max-h-48 overflow-auto rounded-md border border-slate-200 bg-slate-950 p-3 font-mono text-[11px] text-slate-100">
                            {JSON.stringify(exportResult.json_payload, null, 2)}
                          </pre>
                        </TabsContent>
                      </Tabs>
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
