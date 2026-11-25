export interface InvoiceLineItem {
  description: string;
  quantity: number;
  unit_price: number;
  line_total: number;
}

export interface ExtractedInvoice {
  vendor_name: string;
  invoice_number: string;
  invoice_date: string;
  due_date: string | null;
  property_address: string;
  line_items: InvoiceLineItem[];
  subtotal: number;
  tax_amount: number;
  discount_amount: number;
  amount_due: number;
  extraction_confidence: number;
}

export interface GLRecommendation {
  gl_code: string;
  gl_account_name: string;
  gl_confidence: number;
  explanation: string;
}

export interface ValidationReport {
  math_valid: boolean;
  math_discrepancy: number;
  status: "VALID" | "NEEDS_REVIEW";
  warnings: string[];
}

export interface InvoiceAnalysisResponse {
  trace_id: string | null;
  extraction_mode: "text" | "vision";
  invoice: ExtractedInvoice;
  gl_recommendation: GLRecommendation;
  validation: ValidationReport;
}

export interface ChartOfAccountsEntry {
  gl_code: string;
  account_name: string;
  examples: string;
}

export interface YardiExportPayload {
  batch_id: string;
  vendor_name: string;
  invoice_number: string;
  invoice_date: string;
  property_address: string;
  gl_code: string;
  gl_account_name: string;
  amount_due: number;
  human_approved: boolean;
  approved_by: string;
  langfuse_trace_id: string | null;
}

export interface YardiExportResponse {
  csv_content: string;
  filename: string;
  json_payload: YardiExportPayload & { approved_at: string };
}

export interface HealthResponse {
  status: string;
  langfuse_enabled: boolean;
}
