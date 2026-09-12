import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface Attachment { id: number; name: string; file: string; uploaded_at: string; }
export interface Contract {
  id: number; name: string; source_type: string; source_type_display: string;
  total_amount: string; period_start: string; period_end: string;
  received_date: string; attachments: Attachment[];
}
export interface Rule {
  id: number; contract: number; version_no: number; is_active: boolean;
  scope_type: string; method: string; exclude_vacant: boolean;
  shortfall_policy: string; publication_days: number; buildings: number[];
}
export interface Dispute { id: number; amount: string; reason: string; status: string; }
export interface Adjustment { id: number; delta: string; reason: string; created_at: string; }
export interface Detail {
  id: number; unit_code: string; building_name: string; owner_name: string;
  ownership_period: number | null; slice_start: string; slice_end: string;
  share: string; amount: string; remainder_applied: boolean;
  frozen_amount: string; payable: string; disputes: Dispute[]; adjustments: Adjustment[];
}
export interface Version {
  id: number; rule: number; contract_id: number; contract_name: string;
  rule_version_no: number; version_no: number; status: string; status_display: string;
  allocated_total: string; unallocated_amount: string;
  computed_at: string; published_at: string | null;
  details: Detail[];
  carry_forward: { amount: string; frozen_total: string; carried_at: string; adjustments: Adjustment[] } | null;
}
export interface Trace {
  contract: { id: number; name: string; total_amount: string; period_start: string; period_end: string; received_date: string; };
  rule_version: number;
  details: Detail[];
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);
  private base = '/api';

  contracts(): Observable<Contract[]> { return this.http.get<Contract[]>(`${this.base}/contracts/`); }
  contract(id: number): Observable<Contract> { return this.http.get<Contract>(`${this.base}/contracts/${id}/`); }
  uploadAttachment(contractId: number, file: File, name: string) {
    const fd = new FormData();
    fd.append('file', file); fd.append('name', name);
    return this.http.post(`${this.base}/contracts/${contractId}/attachments/`, fd);
  }
  rules(): Observable<Rule[]> { return this.http.get<Rule[]>(`${this.base}/rules/`); }
  generate(ruleId: number): Observable<Version> { return this.http.post<Version>(`${this.base}/rules/${ruleId}/generate/`, {}); }
  versions(): Observable<Version[]> { return this.http.get<Version[]>(`${this.base}/versions/`); }
  version(id: number): Observable<Version> { return this.http.get<Version>(`${this.base}/versions/${id}/`); }
  trace(id: number): Observable<Trace> { return this.http.get<Trace>(`${this.base}/versions/${id}/trace/`); }
  publish(id: number): Observable<Version> { return this.http.post<Version>(`${this.base}/versions/${id}/publish/`, {}); }
  carryForward(id: number, note: string) { return this.http.post(`${this.base}/versions/${id}/carry_forward/`, { note }); }
  dispute(detailId: number, amount: string, reason: string) {
    return this.http.post(`${this.base}/details/${detailId}/disputes/`, { amount, reason });
  }
  adjust(versionId: number, detailId: number, delta: string, reason: string) {
    return this.http.post(`${this.base}/versions/${versionId}/adjustments/`, { detail: detailId, delta, reason });
  }
}
