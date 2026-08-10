import { client, downloadAuthorizedFile } from '@/lib/localApi';
import type { Company, FinancialAccess, PricingItem, ReportLine, StatementGridRow } from '@/types/financialErp';

const invoke = async <T>(url:string, method='GET', data?:unknown): Promise<T> =>
  (await client.apiCall.invoke({ url, method, data })).data as T;

export const financialErpApi = {
  access: () => invoke<FinancialAccess>('/api/v1/admin/financial/access'),
  companies: () => invoke<{items:Company[]}>('/api/v1/admin/financial/companies'),
  pricingItems: (companyId:number) => invoke<{items:PricingItem[]}>(`/api/v1/admin/financial/pricing-items?company_id=${companyId}`),
  createPricingItem: (companyId:number, data:unknown) => invoke(`/api/v1/admin/financial/companies/${companyId}/pricing-items`, 'POST', data),
  statementGrid: (companyId:number, year:number, month:number) =>
    invoke<{statement_id:number|null;status:string;items:StatementGridRow[]}>(`/api/v1/admin/financial/statements/grid?company_id=${companyId}&accounting_year=${year}&accounting_month=${month}`),
  saveStatement: (data:unknown) => invoke<{statement_id:number;status:string;saved:number}>('/api/v1/admin/financial/statements/bulk','PUT',data),
  approveStatement: (id:number) => invoke(`/api/v1/admin/financial/statements/${id}/approve`,'POST'),
  reopenStatement: (id:number,reason:string) => invoke(`/api/v1/admin/financial/statements/${id}/reopen`,'POST',{reason}),
  dashboard: (year:number,month:number) => invoke<any>(`/api/v1/admin/financial/dashboard/erp?accounting_year=${year}&accounting_month=${month}`),
  report: (query:string) => invoke<{items:ReportLine[];totals:Record<string,number>}>(`/api/v1/admin/financial/reports/lines?${query}`),
  exportReport: (query:string) => downloadAuthorizedFile(`/api/v1/admin/financial/reports/lines.xlsx?${query}`,'mfec-financial-report.xlsx'),
  settlements: () => invoke<{items:any[]}>('/api/v1/admin/financial/settlements'),
  createSettlement: (data:unknown) => invoke('/api/v1/admin/financial/settlements','POST',data),
  revenues: () => invoke<{items:any[]}>('/api/v1/admin/financial/revenues'),
  createRevenue: (data:unknown) => invoke('/api/v1/admin/financial/revenues','POST',data),
};
