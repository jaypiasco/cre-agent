import type {
  ChartOfAccountsEntry,
  HealthResponse,
  InvoiceAnalysisResponse,
  LlmClientConfig,
  YardiExportPayload,
  YardiExportResponse,
} from "./types";

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");

const N8N_WEBHOOK_URL = (
  process.env.NEXT_PUBLIC_N8N_WEBHOOK_URL || ""
).replace(/\/$/, "");

async function safeFetch(url: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch (err) {
    if (err instanceof TypeError) {
      throw new Error(
        `Could not reach CRE-Agent service (${url}). Please verify the backend or n8n webhook is running and reachable.`
      );
    }
    throw err;
  }
}

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    const raw =
      typeof body?.detail === "string" ? body.detail : JSON.stringify(body);
    if (/503\s*UNAVAILABLE|high demand|temporarily overloaded/i.test(raw)) {
      return "Gemini model is temporarily overloaded (503 UNAVAILABLE). Please retry in a moment.";
    }
    return raw;
  } catch {
    return `Request failed with status ${res.status}`;
  }
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await safeFetch(`${API_BASE_URL}/health`, { cache: "no-store" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function fetchChartOfAccounts(): Promise<ChartOfAccountsEntry[]> {
  const res = await safeFetch(`${API_BASE_URL}/api/v1/chart-of-accounts`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function analyzeInvoicePdf(
  file: File,
  llmConfig?: LlmClientConfig
): Promise<InvoiceAnalysisResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const headers: Record<string, string> = {};
  if (llmConfig) {
    headers["X-LLM-Provider"] = llmConfig.mode;
    if (llmConfig.mode !== "mock" && llmConfig.apiKey.trim()) {
      headers["X-LLM-Api-Key"] = llmConfig.apiKey.trim();
    }
  }

  const targetUrl =
    N8N_WEBHOOK_URL || `${API_BASE_URL}/api/v1/invoices/analyze`;

  const res = await safeFetch(targetUrl, {
    method: "POST",
    headers,
    body: formData,
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function exportYardiInvoice(
  payload: YardiExportPayload
): Promise<YardiExportResponse> {
  const res = await safeFetch(`${API_BASE_URL}/api/v1/invoices/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}
