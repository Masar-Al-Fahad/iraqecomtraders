import { useEffect, useMemo, useState } from 'react';
import { Download, Edit3, ExternalLink, Eye, FileText, Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { financialErpApi } from '@/lib/financialErpApi';
import type { AccountItem, Attachment, Company, MemberAccount, MemberOption, PricingItem, ServiceType } from '@/types/financialErp';
import { CompactTable, Empty, FileButton, FormDialog, PageTitle, SafeDateInput, SearchBox, StatusBadge, money } from './FinancialUi';

type Common={companies:Company[];services:ServiceType[];reloadCompanies:()=>Promise<void>;can:(key:string)=>boolean;notify:(e:unknown)=>void;success:(message:string)=>void};
const date=()=>new Date().toISOString().slice(0,10);
const blankCompany={name:'',service_type_id:'',owner_name:'',address:'',mobile:'',contact_info:'',cooperation_started_at:'',cooperation_status:'active',status:'active',contract_start:'',contract_end:'',notes:''};
const blankPrice={name:'',unit:'',company_unit_price:'',mfec_share_type:'fixed',mfec_share_value:'',effective_from:date(),effective_to:'',notes:''};

export function CompaniesPage({companies,services,reloadCompanies,can,notify,success}:Common){
  const [search,setSearch]=useState('');const [status,setStatus]=useState('all');
  const [companyOpen,setCompanyOpen]=useState(false);const [selected,setSelected]=useState<Company>();
  const [form,setForm]=useState<any>(blankCompany);const [pricing,setPricing]=useState<PricingItem[]>([]);
  const [priceOpen,setPriceOpen]=useState(false);const [editPrice,setEditPrice]=useState<PricingItem>();
  const [priceForm,setPriceForm]=useState<any>(blankPrice);const [priceHistory,setPriceHistory]=useState<any[]>([]);const [attachments,setAttachments]=useState<Attachment[]>([]);
  const filtered=useMemo(()=>companies.filter(x=>(status==='all'||x.cooperation_status===status)&&
    [x.name,x.service_type_name,x.owner_name,x.mobile].some(v=>v?.toLowerCase().includes(search.toLowerCase()))),[companies,search,status]);
  const openCompany=async(company?:Company)=>{
    setSelected(company);setForm(company?{...blankCompany,...company,service_type_id:String(company.service_type_id)}:blankCompany);
    setCompanyOpen(true);if(company)await Promise.all([
      financialErpApi.pricingItems(company.id).then(x=>setPricing(x.items)),
      financialErpApi.companyAttachments(company.id).then(x=>setAttachments(x.items)),
    ]).catch(notify);else{setPricing([]);setAttachments([])}
  };
  const saveCompany=async()=>{if(form.name.trim().length<2){notify(new Error('اسم الشركة مطلوب ويجب أن يتكون من حرفين على الأقل'));return}if(!form.service_type_id){notify(new Error('اختر نشاط الشركة / نوع الخدمة'));return}try{
    await financialErpApi.saveCompany({...form,service_type_id:Number(form.service_type_id),
      cooperation_started_at:form.cooperation_started_at||null,contract_start:form.contract_start||null,contract_end:form.contract_end||null},selected?.id);
    await reloadCompanies();setCompanyOpen(false);success(selected?'تم تحديث بيانات الشركة وحفظها':'تم إنشاء الشركة وحفظها؛ افتح ملفها لإضافة البنود والعقود');
  }catch(e){notify(e)}};
  const savePrice=async()=>{if(!selected)return;if(!priceForm.name?.trim()&&!editPrice){notify(new Error('اسم فقرة التحاسب مطلوب'));return}if(!priceForm.unit?.trim()&&!editPrice){notify(new Error('وحدة القياس مطلوبة'));return}if(priceForm.company_unit_price===''||priceForm.mfec_share_value===''){notify(new Error('أدخل سعر الشركة وقيمة حصة MFEC'));return}try{
    const payload={...priceForm,company_unit_price:Number(priceForm.company_unit_price),mfec_share_value:Number(priceForm.mfec_share_value),effective_to:priceForm.effective_to||null};
    if(editPrice)await financialErpApi.createPricingVersion(editPrice.id,{...payload,name:editPrice.name,unit:editPrice.unit});
    else await financialErpApi.createPricingItem(selected.id,payload);
    setPricing((await financialErpApi.pricingItems(selected.id)).items);setPriceOpen(false);success(editPrice?'تم إنشاء نسخة سعر تاريخية جديدة':'تمت إضافة فقرة التحاسب');
  }catch(e){notify(e)}};
  const uploadAttachment=async(file:File,replacedId?:number)=>{if(!selected)return;try{
    const up=await financialErpApi.upload('contracts',file);
    await financialErpApi.addCompanyAttachment(selected.id,{...up,original_filename:file.name,mime_type:file.type,size_bytes:file.size,document_type:'contract',replaced_id:replacedId||null});
    setAttachments((await financialErpApi.companyAttachments(selected.id)).items);
  }catch(e){notify(e)}};
  return <div className="space-y-4">
    <PageTitle title="الشركات والعقود" description="ملف الشركة، فقرات التحاسب المؤرخة، ونسخ العقود الأصلية."
      actions={can('financial.companies.create')&&<Button onClick={()=>openCompany()}><Plus className="w-4 h-4 ml-2"/>شركة جديدة</Button>}/>
    <Card><CardContent className="p-3 flex gap-2 flex-wrap"><SearchBox value={search} onChange={setSearch} placeholder="اسم الشركة، المالك، الهاتف..."/>
      <select className="h-10 border rounded-md px-3 bg-white" value={status} onChange={e=>setStatus(e.target.value)}><option value="all">كل الحالات</option><option value="active">متعاون</option><option value="suspended">معلق</option><option value="ended">منتهي</option></select>
      <span className="text-sm text-slate-500 self-center">{filtered.length} شركة</span></CardContent></Card>
    <CompactTable headers={['الشركة','الخدمة','المالك والاتصال','بدء التعاون','الحالة','الإجراءات']}>
      {filtered.map(c=><tr key={c.id} className="border-t hover:bg-slate-50"><td className="p-3"><b>{c.name}</b><small className="block text-slate-500 max-w-64 truncate">{c.address||c.notes||'-'}</small></td>
        <td>{c.service_type_name}</td><td>{c.owner_name||'-'}<small className="block">{c.mobile||'-'}</small></td><td>{c.cooperation_started_at||'-'}</td><td><StatusBadge value={c.cooperation_status}/></td>
        <td className="p-2"><Button size="sm" variant="outline" onClick={()=>openCompany(c)}><Eye className="w-4 h-4 ml-1"/>فتح</Button></td></tr>)}
      {!filtered.length&&<tr><td colSpan={6}><Empty/></td></tr>}
    </CompactTable>
    <FormDialog open={companyOpen} onOpenChange={setCompanyOpen} title={selected?`ملف شركة: ${selected.name}`:'إضافة شركة'} className="max-w-5xl">
      <div className="grid md:grid-cols-3 gap-3">
        <Field label="اسم الشركة"><Input value={form.name} onChange={e=>setForm({...form,name:e.target.value})}/></Field>
        <Field label="نوع الخدمة"><select className="w-full h-10 border rounded-md px-3" value={form.service_type_id} onChange={e=>setForm({...form,service_type_id:e.target.value})}><option value="">اختر</option>{services.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></Field>
        <Field label="اسم المالك"><Input value={form.owner_name||''} onChange={e=>setForm({...form,owner_name:e.target.value})}/></Field>
        <Field label="الهاتف"><Input value={form.mobile||''} onChange={e=>setForm({...form,mobile:e.target.value})}/></Field>
        <Field label="تاريخ التعاون"><SafeDateInput value={form.cooperation_started_at||''} onChange={e=>setForm({...form,cooperation_started_at:e.target.value})}/></Field>
        <Field label="حالة التعاون"><select className="w-full h-10 border rounded-md px-3" value={form.cooperation_status} onChange={e=>setForm({...form,cooperation_status:e.target.value})}><option value="active">متعاون</option><option value="suspended">معلق</option><option value="ended">منتهي</option></select></Field>
        <Field label="العنوان" className="md:col-span-2"><Input value={form.address||''} onChange={e=>setForm({...form,address:e.target.value})}/></Field>
        <Field label="الحالة النظامية"><select className="w-full h-10 border rounded-md px-3" value={form.status} onChange={e=>setForm({...form,status:e.target.value})}><option value="active">فعال</option><option value="inactive">غير فعال</option></select></Field>
        <Field label="معلومات الاتصال" className="md:col-span-3"><Textarea value={form.contact_info||''} onChange={e=>setForm({...form,contact_info:e.target.value})}/></Field>
        <Field label="ملاحظات" className="md:col-span-3"><Textarea value={form.notes||''} onChange={e=>setForm({...form,notes:e.target.value})}/></Field>
      </div>
      {(selected?can('financial.companies.edit'):can('financial.companies.create'))&&<Button type="button" onClick={saveCompany}>حفظ بيانات الشركة</Button>}
      {selected&&<div className="border-t pt-4 space-y-3">
        <div className="flex justify-between items-center"><h3 className="font-bold">فقرات التحاسب</h3>{can('financial.pricing.manage')&&<Button size="sm" onClick={()=>{setEditPrice(undefined);setPriceForm(blankPrice);setPriceOpen(true)}}><Plus className="w-4 h-4 ml-1"/>فقرة</Button>}</div>
        <CompactTable headers={['الفقرة','الوحدة','سعر الشركة','حصة MFEC','النسخة/النفاذ','']}>{pricing.map(p=><tr key={p.id} className="border-t"><td className="p-2">{p.name}</td><td>{p.unit}</td><td>{money(p.current_version?.company_unit_price)}</td><td>{p.current_version?.mfec_share_type==='percentage'?`${p.current_version.mfec_share_value}%`:money(p.current_version?.mfec_share_value)}</td><td>v{p.current_version?.version} · {p.current_version?.effective_from}</td><td><Button size="sm" variant="ghost" onClick={async()=>{setEditPrice(p);setPriceForm({...blankPrice,...p.current_version,name:p.name,unit:p.unit,effective_to:p.current_version?.effective_to||''});setPriceHistory((await financialErpApi.pricingVersions(p.id)).items);setPriceOpen(true)}}><Edit3 className="w-4 h-4"/></Button></td></tr>)}</CompactTable>
      </div>}
      {selected&&<div className="border-t pt-4 space-y-3"><div className="flex justify-between"><h3 className="font-bold">مرفقات العقود الأصلية</h3>{can('financial.contracts.manage')&&<FileButton onFile={uploadAttachment}/>}</div>
        {attachments.map(a=><div key={a.id} className="border rounded-lg p-2 flex justify-between items-center"><span><FileText className="w-4 h-4 inline ml-2"/>{a.original_filename}</span><div className="flex items-center"><Button size="icon" variant="ghost" onClick={()=>financialErpApi.openDocument(a.object_key)}><Eye className="w-4 h-4"/></Button><Button size="icon" variant="ghost" onClick={()=>financialErpApi.openDocument(a.object_key,a.original_filename)}><Download className="w-4 h-4"/></Button>{can('financial.contracts.manage')&&<FileButton label="استبدال" onFile={file=>uploadAttachment(file,a.id)}/>} {can('financial.contracts.manage')&&<Button size="icon" variant="ghost" onClick={async()=>{await financialErpApi.deleteCompanyAttachment(selected.id,a.id);setAttachments((await financialErpApi.companyAttachments(selected.id)).items)}}><Trash2 className="w-4 h-4 text-red-600"/></Button>}</div></div>)}
        {!attachments.length&&<Empty title="لا توجد عقود مرفقة" description="يمكن رفع عدة ملفات PDF أو Office أو صور."/>}
      </div>}
    </FormDialog>
    <FormDialog open={priceOpen} onOpenChange={setPriceOpen} title={editPrice?`نسخة سعر جديدة: ${editPrice.name}`:'فقرة تحاسب جديدة'}>
      <div className="grid md:grid-cols-2 gap-3">{!editPrice&&<><Field label="اسم الفقرة"><Input value={priceForm.name} onChange={e=>setPriceForm({...priceForm,name:e.target.value})}/></Field><Field label="الوحدة"><Input value={priceForm.unit} onChange={e=>setPriceForm({...priceForm,unit:e.target.value})}/></Field></>}
        <Field label="سعر الشركة"><Input type="number" value={priceForm.company_unit_price} onChange={e=>setPriceForm({...priceForm,company_unit_price:e.target.value})}/></Field>
        <Field label="نوع حصة MFEC"><select className="w-full h-10 border rounded-md px-3" value={priceForm.mfec_share_type} onChange={e=>setPriceForm({...priceForm,mfec_share_type:e.target.value})}><option value="fixed">مبلغ ثابت</option><option value="percentage">نسبة مئوية</option></select></Field>
        <Field label="قيمة الحصة"><Input type="number" value={priceForm.mfec_share_value} onChange={e=>setPriceForm({...priceForm,mfec_share_value:e.target.value})}/></Field>
        <Field label="نافذ من"><SafeDateInput value={priceForm.effective_from} onChange={e=>setPriceForm({...priceForm,effective_from:e.target.value})}/></Field>
        <Field label="نافذ إلى"><SafeDateInput value={priceForm.effective_to} onChange={e=>setPriceForm({...priceForm,effective_to:e.target.value})}/></Field>
      </div>{editPrice&&<div className="border rounded-lg overflow-hidden"><h4 className="font-bold p-2 bg-slate-50">سجل النسخ الفعالة</h4>{priceHistory.map(v=><div key={v.id} className="grid grid-cols-4 gap-2 p-2 border-t text-sm"><span>v{v.version}</span><span>{v.effective_from} — {v.effective_to||'مستمر'}</span><span>{money(v.company_unit_price)}</span><span>{v.mfec_share_type==='percentage'?`${v.mfec_share_value}%`:money(v.mfec_share_value)}</span></div>)}</div>} {can('financial.pricing.manage')&&<Button type="button" onClick={savePrice}>حفظ النسخة</Button>}
    </FormDialog>
  </div>;
}

const blankAccount={member_id:'',company_id:'',registered_name:'',registered_phone:'',customer_code:'',customer_portal_url:'',started_at:date(),ended_at:'',status:'active',default_unit_price_override:'',default_mfec_share_type_override:'',default_mfec_share_value_override:'',notes:'',is_active:true};
export function MemberLinksPage({companies,can,notify,success,finance}:Omit<Common,'services'|'reloadCompanies'>&{finance:boolean}){
  const [accounts,setAccounts]=useState<MemberAccount[]>([]);const [members,setMembers]=useState<MemberOption[]>([]);
  const [summaries,setSummaries]=useState<Record<number,AccountItem[]>>({});
  const [search,setSearch]=useState('');const [companyFilter,setCompanyFilter]=useState('');const [selected,setSelected]=useState<MemberAccount>();
  const [open,setOpen]=useState(false);const [form,setForm]=useState<any>(blankAccount);const [pricing,setPricing]=useState<PricingItem[]>([]);
  const [items,setItems]=useState<AccountItem[]>([]);const [annexes,setAnnexes]=useState<Attachment[]>([]);const [annexDate,setAnnexDate]=useState(date());
  const load=async()=>{try{const x=await financialErpApi.memberAccounts(financialErpApi.query({company_id:companyFilter,search}));setAccounts(x.items);
    const pairs=await Promise.all(x.items.map(async a=>[a.id,(await financialErpApi.accountItems(a.id)).items] as const));setSummaries(Object.fromEntries(pairs));
  }catch(e){notify(e)}};
  useEffect(()=>{load()},[companyFilter]);useEffect(()=>{if(can('financial.member_links.create'))financialErpApi.members().then(x=>setMembers(x.items)).catch(notify)},[]);
  const openAccount=async(account?:MemberAccount)=>{setSelected(account);setForm(account?{...blankAccount,...account,member_id:String(account.member_id),company_id:String(account.company_id)}:blankAccount);setOpen(true);
    if(account){const [p,i,a]=await Promise.all([financialErpApi.pricingItems(account.company_id),financialErpApi.accountItems(account.id),financialErpApi.annexes(account.id)]);setPricing(p.items);setItems(i.items);setAnnexes(a.items)}else{setPricing([]);setItems([]);setAnnexes([])}};
  const save=async()=>{if(!form.member_id){notify(new Error('اختر العضو من سجل العضويات'));return}if(!form.company_id){notify(new Error('اختر شركة النشاط'));return}try{const payload={...form,member_id:Number(form.member_id),company_id:Number(form.company_id),started_at:form.started_at||null,ended_at:form.ended_at||null,
      default_unit_price_override:form.default_unit_price_override===''?null:Number(form.default_unit_price_override),default_mfec_share_type_override:form.default_mfec_share_type_override||null,default_mfec_share_value_override:form.default_mfec_share_value_override===''?null:Number(form.default_mfec_share_value_override)};
    const result:any=await financialErpApi.saveMemberAccount(payload);await load();if(!selected){const fresh=(await financialErpApi.memberAccounts(financialErpApi.query({member_id:payload.member_id,company_id:payload.company_id}))).items[0];if(fresh)await openAccount(fresh);else setOpen(false)}else setOpen(false);
    success('تم حفظ ارتباط العضو واسترجاعه من قاعدة البيانات');void result;
  }catch(e){notify(e)}};
  const toggleItem=(p:PricingItem,checked:boolean)=>setItems(old=>checked?[...old,{id:0,pricing_item_id:p.id,name:p.name,unit:p.unit,is_active:true}]:old.filter(x=>x.pricing_item_id!==p.id));
  const saveItems=async()=>{if(!selected)return;try{await financialErpApi.saveAccountItems(selected.id,items.map(x=>({pricing_item_id:x.pricing_item_id,unit_price_override:x.unit_price_override??null,mfec_share_type_override:x.mfec_share_type_override||null,mfec_share_value_override:x.mfec_share_value_override??null,is_active:x.is_active,started_at:null,ended_at:null,notes:null})));setItems((await financialErpApi.accountItems(selected.id)).items);success('تم حفظ الفقرات والأسعار الفعالة للعضو')}catch(e){notify(e)}};
  const uploadAnnex=async(file:File,replacedId?:number)=>{if(!selected)return;try{const up=await financialErpApi.upload('annexes',file);await financialErpApi.addAnnex(selected.id,{...up,original_filename:file.name,mime_type:file.type,size_bytes:file.size,signed_at:annexDate||null,replaced_id:replacedId||null});setAnnexes((await financialErpApi.annexes(selected.id)).items);success('تم رفع ملحق الاتفاق الثلاثي')}catch(e){notify(e)}};
  return <div className="space-y-4">
    <PageTitle title="ارتباطات الأعضاء" description="حسابات الأعضاء لدى الشركات، الفقرات الفعالة، الاستثناءات والملحق الثلاثي." actions={can('financial.member_links.create')&&<Button onClick={()=>openAccount()}><Plus className="w-4 h-4 ml-2"/>ارتباط جديد</Button>}/>
    <Card><CardContent className="p-3 flex gap-2 flex-wrap"><SearchBox value={search} onChange={setSearch} placeholder="العضو، رقم العضوية، كود العميل..."/><Button variant="outline" onClick={load}>بحث</Button><select className="h-10 border rounded-md px-3" value={companyFilter} onChange={e=>setCompanyFilter(e.target.value)}><option value="">كل الشركات</option>{companies.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></CardContent></Card>
    <CompactTable headers={['العضو / النشاط','المحافظة','الشركة / الخدمة','الفقرات الفعالة','بيانات التسجيل','بدء الارتباط','الحالة','الرابط','']}>{accounts.map(a=><tr key={a.id} className="border-t"><td className="p-3"><b>{a.member_name}</b><small className="block">{a.business_name} · {a.membership_number}</small></td><td>{a.governorate}</td><td>{a.company_name}<small className="block">{a.service_type_name}</small></td><td>{summaries[a.id]?.map(x=><div key={x.id}>{x.name} ({x.unit}){finance&&<small> · {money(x.effective_unit_price)} / {x.effective_mfec_share_type==='percentage'?`${x.effective_mfec_share_value}%`:money(x.effective_mfec_share_value)}</small>}</div>)||'-'}</td><td>{a.registered_name||'-'}<small className="block">{a.registered_phone} · {a.customer_code}</small></td><td>{a.started_at||'-'}</td><td><StatusBadge value={a.status}/></td><td>{a.customer_portal_url&&<Button size="sm" variant="outline" onClick={()=>window.open(a.customer_portal_url,'_blank','noopener,noreferrer')}><ExternalLink className="w-4 h-4"/></Button>}</td><td><Button size="sm" variant="ghost" onClick={()=>openAccount(a)}><Edit3 className="w-4 h-4"/></Button></td></tr>)}</CompactTable>
    <FormDialog open={open} onOpenChange={setOpen} title={selected?`حساب ${selected.member_name} لدى ${selected.company_name}`:'ارتباط عضو بشركة'} className="max-w-5xl">
      <div className="grid md:grid-cols-3 gap-3"><Field label="العضو"><select disabled={!!selected} className="w-full h-10 border rounded-md px-3" value={form.member_id} onChange={e=>setForm({...form,member_id:e.target.value})}><option value="">اختر</option>{members.map(m=><option key={m.id} value={m.id}>{m.membership_number} · {m.member_name} · {m.business_name}</option>)}</select></Field>
        <Field label="الشركة"><select disabled={!!selected} className="w-full h-10 border rounded-md px-3" value={form.company_id} onChange={e=>setForm({...form,company_id:e.target.value})}><option value="">اختر</option>{companies.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
        <Field label="الحالة"><select className="w-full h-10 border rounded-md px-3" value={form.status} onChange={e=>setForm({...form,status:e.target.value,is_active:e.target.value==='active'})}><option value="active">فعال</option><option value="inactive">غير فعال</option><option value="suspended">معلق</option></select></Field>
        <Field label="الاسم المسجل"><Input value={form.registered_name||''} onChange={e=>setForm({...form,registered_name:e.target.value})}/></Field><Field label="الهاتف المسجل"><Input value={form.registered_phone||''} onChange={e=>setForm({...form,registered_phone:e.target.value})}/></Field><Field label="كود العميل"><Input value={form.customer_code||''} onChange={e=>setForm({...form,customer_code:e.target.value})}/></Field>
        <Field label="رابط بوابة العميل" className="md:col-span-2"><Input dir="ltr" value={form.customer_portal_url||''} onChange={e=>setForm({...form,customer_portal_url:e.target.value})}/></Field><Field label="تاريخ البدء"><SafeDateInput value={form.started_at||''} onChange={e=>setForm({...form,started_at:e.target.value})}/></Field>
        <Field label="سعر افتراضي خاص"><Input type="number" value={form.default_unit_price_override||''} onChange={e=>setForm({...form,default_unit_price_override:e.target.value})}/></Field><Field label="نوع حصة افتراضية"><select className="w-full h-10 border rounded-md px-3" value={form.default_mfec_share_type_override||''} onChange={e=>setForm({...form,default_mfec_share_type_override:e.target.value})}><option value="">سعر الشركة</option><option value="fixed">ثابت</option><option value="percentage">نسبة</option></select></Field><Field label="قيمة حصة افتراضية"><Input type="number" value={form.default_mfec_share_value_override||''} onChange={e=>setForm({...form,default_mfec_share_value_override:e.target.value})}/></Field>
      </div>{can(selected?'financial.member_links.edit':'financial.member_links.create')&&<Button type="button" onClick={save}>حفظ الحساب</Button>}
      {selected&&<div className="border-t pt-4 space-y-3"><h3 className="font-bold">الفقرات المخصصة للعضو</h3>{pricing.map(p=>{const item=items.find(x=>x.pricing_item_id===p.id);return <div key={p.id} className="grid md:grid-cols-[30px_1fr_1fr_1fr_1fr] gap-2 items-center border rounded-lg p-2"><Checkbox checked={!!item} onCheckedChange={v=>toggleItem(p,!!v)}/><b>{p.name} ({p.unit})</b><Input disabled={!item} type="number" placeholder={`السعر ${p.current_version?.company_unit_price||0}`} value={item?.unit_price_override??''} onChange={e=>setItems(xs=>xs.map(x=>x.pricing_item_id===p.id?{...x,unit_price_override:e.target.value===''?undefined:Number(e.target.value)}:x))}/><select disabled={!item} className="h-10 border rounded-md px-2" value={item?.mfec_share_type_override||''} onChange={e=>setItems(xs=>xs.map(x=>x.pricing_item_id===p.id?{...x,mfec_share_type_override:(e.target.value||undefined) as any}:x))}><option value="">الحصة الأصلية</option><option value="fixed">ثابت</option><option value="percentage">نسبة</option></select><Input disabled={!item} type="number" placeholder="قيمة الحصة" value={item?.mfec_share_value_override??''} onChange={e=>setItems(xs=>xs.map(x=>x.pricing_item_id===p.id?{...x,mfec_share_value_override:e.target.value===''?undefined:Number(e.target.value)}:x))}/></div>})}{can('financial.member_links.edit')&&<Button onClick={saveItems}>حفظ الفقرات والاستثناءات</Button>}</div>}
      {selected&&<div className="border-t pt-4 space-y-2"><div className="flex justify-between items-end gap-2"><h3 className="font-bold">ملحق الاتفاق الثلاثي</h3>{can('financial.annexes.manage')&&<div className="flex items-end gap-2"><Field label="تاريخ التوقيع"><SafeDateInput className="w-40" value={annexDate} onChange={e=>setAnnexDate(e.target.value)}/></Field><FileButton onFile={uploadAnnex}/></div>}</div>{annexes.map(a=><div key={a.id} className="flex justify-between border rounded p-2"><span>{a.original_filename}<small className="block text-slate-500">{a.signed_at?`موقع في ${a.signed_at}`:'دون تاريخ توقيع'}</small></span><div className="flex"><Button size="icon" variant="ghost" onClick={()=>financialErpApi.openDocument(a.object_key)}><Eye className="w-4 h-4"/></Button>{can('financial.annexes.manage')&&<FileButton label="استبدال" onFile={file=>uploadAnnex(file,a.id)}/>} {can('financial.annexes.manage')&&<Button size="icon" variant="ghost" onClick={async()=>{await financialErpApi.deleteAnnex(selected.id,a.id);setAnnexes((await financialErpApi.annexes(selected.id)).items)}}><Trash2 className="w-4 h-4 text-red-600"/></Button>}</div></div>)}</div>}
    </FormDialog>
  </div>;
}

function Field({label,children,className=''}:{label:string;children:React.ReactNode;className?:string}){return <div className={className}><Label className="mb-1 block">{label}</Label>{children}</div>}
