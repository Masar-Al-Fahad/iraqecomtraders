export type PermissionMap = Record<string, boolean>;
export type FinancialAccess = { permissions: PermissionMap; is_super_admin: boolean };
export type ServiceType = { id:number; name:string; code:string };
export type Company = {
  id:number; name:string; service_type_name:string; service_type_id:number; status:string;
  contact_info?:string; contract_start?:string; contract_end?:string; notes?:string;
  owner_name?:string; address?:string; mobile?:string; cooperation_status:string;
  cooperation_started_at?:string;
};
export type PricingItem = {
  id:number; company_id:number; name:string; unit:string; is_active:boolean;
  notes?:string; current_version?: PricingVersion | null;
};
export type PricingVersion = { id:number; version:number; company_unit_price:number; mfec_share_type:'fixed'|'percentage'; mfec_share_value:number; effective_from:string; effective_to?:string };
export type Attachment = { id:number; object_key:string; original_filename:string; mime_type:string; size_bytes?:number; uploaded_at?:string; signed_at?:string };
export type MemberOption = { id:number; member_name:string; business_name?:string; membership_number?:string; governorate:string };
export type MemberAccount = {
  id:number; member_id:number; member_name:string; business_name?:string; membership_number?:string;
  governorate:string; company_id:number; company_name:string; service_type_name:string;
  registered_name?:string; registered_phone?:string; customer_code?:string; customer_portal_url?:string;
  started_at?:string; ended_at?:string; status:string; notes?:string; is_active:boolean;
};
export type AccountItem = {
  id:number; pricing_item_id:number; name:string; unit:string; unit_price_override?:number;
  mfec_share_type_override?:'fixed'|'percentage'; mfec_share_value_override?:number; is_active:boolean;
  effective_unit_price?:number; effective_mfec_share_type?:'fixed'|'percentage';
  effective_mfec_share_value?:number; started_at?:string;
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
export type Settlement = { id:number; batch_number:string; company_id:number; settled_at:string; status:string; reference_number?:string; notes?:string; attachment_key?:string; line_count:number };
export type Revenue = {
  id:number; receipt_number:string; company_id:number; received_at:string; amount:number; allocated:number; remaining:number;
  receipt_method:string; category?:string; description:string; period_start?:string; period_end?:string;
  notes?:string; attachment_key?:string; deleted:boolean;
};
export type Expense = { id:number; expense_date:string; accounting_year:number; accounting_month:number; category:string; description:string; amount:number; notes?:string; receipt_key?:string; created_by:string; deleted:boolean };
