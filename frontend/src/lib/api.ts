import type {
  ChartOfAccountsEntry,
  HealthResponse,
  InvoiceAnalysisResponse,
  YardiExportPayload,
  YardiExportResponse,
} from "./types";

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
    return JSON.stringify(body);
  } catch {
    return `Request failed with status ${res.status}`;
  }
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE_URL}/health`, { cache: "no-store" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function fetchChartOfAccounts(): Promise<ChartOfAccountsEntry[]> {
  const res = await fetch(`${API_BASE_URL}/api/v1/chart-of-accounts`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function analyzeInvoicePdf(
  file: File
): Promise<InvoiceAnalysisResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE_URL}/api/v1/invoices/analyze`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function exportYardiInvoice(
  payload: YardiExportPayload
): Promise<YardiExportResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/invoices/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}
