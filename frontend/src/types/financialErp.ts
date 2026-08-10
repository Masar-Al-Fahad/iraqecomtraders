export type PermissionMap = Record<string, boolean>;
export type FinancialAccess = { permissions: PermissionMap; is_super_admin: boolean };
export type Company = { id:number; name:string; service_type_name:string; service_type_id:number; status:string };
export type PricingItem = {
  id:number; company_id:number; name:string; unit:string; is_active:boolean;
  current_version?: { id:number; company_unit_price:number; mfec_share_type:'fixed'|'percentage'; mfec_share_value:number } | null;
};
export type StatementGridRow = {
  account_item_id:number; member_id:number; member_name:string; business_name?:string;
  membership_number?:string; governorate:string; registered_name?:string; registered_phone?:string;
  customer_code?:string; customer_portal_url?:string; pricing_item_id:number;
  pricing_item_name:string; unit:string; quantity:number; excluded:boolean;
  gross_business_amount?:number; mfec_due_amount?:number; settlement_status?:string;
};
export type ReportLine = {
  id:number; company_name:string; service_type:string; member_name:string; membership_number?:string;
  governorate:string; pricing_item:string; unit:string; quantity:number; unit_price:number;
  gross_business_amount:number; mfec_due_amount:number; settlement_status:'settled'|'unsettled';
  settled_amount:number; received_amount:number; outstanding_receivable:number;
};
