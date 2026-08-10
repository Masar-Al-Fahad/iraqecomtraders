import { client, downloadAuthorizedFile, getApiBase, localAuth } from '@/lib/localApi';
import type {
  AccountItem, Attachment, Company, Expense, FinancialAccess, MemberAccount, MemberOption,
  PricingItem, ReportLine, Revenue, ServiceType, Settlement, StatementGridRow,
} from '@/types/financialErp';

const invoke = async <T>(url:string, method='GET', data?:unknown): Promise<T> =>
  (await client.apiCall.invoke({ url, method, data })).data as T;

const qs=(values:Record<string,unknown>)=>{
  const q=new URLSearchParams();
  Object.entries(values).forEach(([key,value])=>{
    if(value!==undefined&&value!==null&&value!=='') {
      if(Array.isArray(value)) value.forEach(x=>q.append(key,String(x))); else q.set(key,String(value));
    }
  });
  return q.toString();
};

async function upload(kind:string,file:File){
  const form=new FormData();form.append('file',file);
  const res=await fetch(`${getApiBase()}/api/v1/admin/financial/documents/${kind}`,{
    method:'POST',headers:{Authorization:`Bearer ${localAuth.getToken()||''}`},body:form,
  });
  if(!res.ok)throw new Error((await res.json().catch(()=>({})))?.detail||'فشل رفع المستند');
  return (await res.json()) as {object_key:string};
}

async function openDocument(objectKey:string,filename?:string){
  const res=await fetch(`${getApiBase()}/api/v1/admin/financial/documents?${qs({object_key:objectKey})}`,{
    headers:{Authorization:`Bearer ${localAuth.getToken()||''}`},
  });
  if(!res.ok)throw new Error('تعذر فتح المستند');
  const url=URL.createObjectURL(await res.blob());
  if(filename){const a=document.createElement('a');a.href=url;a.download=filename;a.click();}
  else window.open(url,'_blank','noopener,noreferrer');
  setTimeout(()=>URL.revokeObjectURL(url),60_000);
}

export const financialErpApi = {
  access: () => invoke<FinancialAccess>('/api/v1/admin/financial/access'),
  serviceTypes:()=>invoke<{items:ServiceType[]}>('/api/v1/admin/financial/service-types'),
  companies: () => invoke<{items:Company[]}>('/api/v1/admin/financial/companies'),
  saveCompany:(data:unknown,id?:number)=>invoke(id?`/api/v1/admin/financial/companies/${id}`:'/api/v1/admin/financial/companies',id?'PUT':'POST',data),
  pricingItems: (companyId:number) => invoke<{items:PricingItem[]}>(`/api/v1/admin/financial/pricing-items?company_id=${companyId}`),
  createPricingItem: (companyId:number, data:unknown) => invoke(`/api/v1/admin/financial/companies/${companyId}/pricing-items`, 'POST', data),
  createPricingVersion:(itemId:number,data:unknown)=>invoke(`/api/v1/admin/financial/pricing-items/${itemId}/versions`,'POST',data),
  pricingVersions:(itemId:number)=>invoke<{items:any[]}>(`/api/v1/admin/financial/pricing-items/${itemId}/versions`),
  companyAttachments:(companyId:number)=>invoke<{items:Attachment[]}>(`/api/v1/admin/financial/companies/${companyId}/attachments`),
  addCompanyAttachment:(companyId:number,data:unknown)=>invoke(`/api/v1/admin/financial/companies/${companyId}/attachments`,'POST',data),
  deleteCompanyAttachment:(companyId:number,id:number)=>invoke(`/api/v1/admin/financial/companies/${companyId}/attachments/${id}`,'DELETE'),
  members:()=>invoke<{items:MemberOption[]}>('/api/v1/admin/financial/members'),
  memberAccounts:(query='')=>invoke<{items:MemberAccount[]}>(`/api/v1/admin/financial/member-accounts${query?`?${query}`:''}`),
  saveMemberAccount:(data:unknown)=>invoke('/api/v1/admin/financial/member-accounts','POST',data),
  accountItems:(id:number)=>invoke<{items:AccountItem[]}>(`/api/v1/admin/financial/member-accounts/${id}/items`),
  saveAccountItems:(id:number,data:unknown)=>invoke(`/api/v1/admin/financial/member-accounts/${id}/items`,'PUT',data),
  annexes:(id:number)=>invoke<{items:Attachment[]}>(`/api/v1/admin/financial/member-accounts/${id}/annexes`),
  addAnnex:(id:number,data:unknown)=>invoke(`/api/v1/admin/financial/member-accounts/${id}/annexes`,'POST',data),
  deleteAnnex:(id:number,annexId:number)=>invoke(`/api/v1/admin/financial/member-accounts/${id}/annexes/${annexId}`,'DELETE'),
  statementGrid: (companyId:number, year:number, month:number) =>
    invoke<{statement_id:number|null;status:string;items:StatementGridRow[]}>(`/api/v1/admin/financial/statements/grid?company_id=${companyId}&accounting_year=${year}&accounting_month=${month}`),
  saveStatement: (data:unknown) => invoke<{statement_id:number;status:string;saved:number}>('/api/v1/admin/financial/statements/bulk','PUT',data),
  approveStatement: (id:number) => invoke(`/api/v1/admin/financial/statements/${id}/approve`,'POST'),
  reopenStatement: (id:number,reason:string) => invoke(`/api/v1/admin/financial/statements/${id}/reopen`,'POST',{reason}),
  statementAttachments:(id:number)=>invoke<{items:Attachment[]}>(`/api/v1/admin/financial/statements/${id}/attachments`),
  addStatementAttachment:(id:number,data:unknown)=>invoke(`/api/v1/admin/financial/statements/${id}/attachments`,'POST',data),
  deleteStatementAttachment:(id:number,attachmentId:number)=>invoke(`/api/v1/admin/financial/statements/${id}/attachments/${attachmentId}`,'DELETE'),
  dashboard: (year:number,month:number) => invoke<any>(`/api/v1/admin/financial/dashboard/erp?accounting_year=${year}&accounting_month=${month}`),
  report: (query:string) => invoke<{items:ReportLine[];totals:Record<string,number>}>(`/api/v1/admin/financial/reports/lines?${query}`),
  exportReport: (query:string) => downloadAuthorizedFile(`/api/v1/admin/financial/reports/lines.xlsx?${query}`,'mfec-financial-report.xlsx'),
  settlements: (companyId?:number) => invoke<{items:Settlement[]}>(`/api/v1/admin/financial/settlements?${qs({company_id:companyId})}`),
  createSettlement: (data:unknown) => invoke('/api/v1/admin/financial/settlements','POST',data),
  reverseSettlement:(id:number,reason:string)=>invoke(`/api/v1/admin/financial/settlements/${id}/reverse`,'POST',{reason}),
  settlementLines:(id:number)=>invoke<{items:any[]}>(`/api/v1/admin/financial/settlements/${id}/lines`),
  revenues: (filters:Record<string,unknown>={}) => invoke<{items:Revenue[]}>(`/api/v1/admin/financial/revenues?${qs(filters)}`),
  createRevenue: (data:unknown) => invoke('/api/v1/admin/financial/revenues','POST',data),
  updateRevenue:(id:number,data:unknown)=>invoke(`/api/v1/admin/financial/revenues/${id}`,'PUT',data),
  deleteRevenue:(id:number)=>invoke(`/api/v1/admin/financial/revenues/${id}`,'DELETE'),
  restoreRevenue:(id:number)=>invoke(`/api/v1/admin/financial/revenues/${id}/restore`,'POST'),
  allocationTargets:(id:number)=>invoke<any>(`/api/v1/admin/financial/revenues/${id}/allocation-targets`),
  allocations:(id:number)=>invoke<{items:any[]}>(`/api/v1/admin/financial/revenues/${id}/allocations`),
  allocateRevenue:(id:number,data:unknown)=>invoke(`/api/v1/admin/financial/revenues/${id}/allocations`,'POST',data),
  exportRevenues:(filters:Record<string,unknown>)=>downloadAuthorizedFile(`/api/v1/admin/financial/revenues.xlsx?${qs(filters)}`,'mfec-revenues.xlsx'),
  expenses:(filters:Record<string,unknown>={})=>invoke<{items:Expense[]}>(`/api/v1/admin/financial/expenses?${qs(filters)}`),
  saveExpense:(data:unknown,id?:number)=>invoke(id?`/api/v1/admin/financial/expenses/${id}`:'/api/v1/admin/financial/expenses',id?'PUT':'POST',data),
  deleteExpense:(id:number)=>invoke(`/api/v1/admin/financial/expenses/${id}`,'DELETE'),
  restoreExpense:(id:number)=>invoke(`/api/v1/admin/financial/expenses/${id}/restore`,'POST'),
  exportExpenses:(filters:Record<string,unknown>)=>downloadAuthorizedFile(`/api/v1/admin/financial/expenses.xlsx?${qs(filters)}`,'mfec-expenses.xlsx'),
  upload,openDocument,query:qs,
};
