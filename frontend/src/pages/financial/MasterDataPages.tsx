import { useEffect, useMemo, useState } from 'react';
import { ChevronDown, Download, Edit3, ExternalLink, Eye, FileText, History, Plus, Trash2 } from 'lucide-react';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { financialErpApi } from '@/lib/financialErpApi';
import type { AccountItem, Attachment, Company, MemberAccount, MemberOption, PricingItem, ServiceType } from '@/types/financialErp';
import { CompactTable, Empty, FileButton, FormDialog, PageTitle, SafeDateInput, SearchBox, StatusBadge, money } from './FinancialUi';

type Common={companies:Company[];services:ServiceType[];reloadCompanies:()=>Promise<void>;can:(key:string)=>boolean;notify:(e:unknown)=>void;success:(message:string)=>void};

const date=()=>new Date().toISOString().slice(0,10);

const ACTIVITY_OPTIONS=[
  {code:'shipping',label:'شحن'},
  {code:'delivery',label:'توصيل'},
  {code:'design',label:'تصاميم'},
  {code:'sorting',label:'فرز'},
  {code:'other',label:'أخرى'},
] as const;

type ActivityCode=typeof ACTIVITY_OPTIONS[number]['code'];

const blankCompany={
  name:'',activity_code:'' as ActivityCode|'',other_activity:'',owner_name:'',address:'',mobile:'',
  contact_info:'',cooperation_started_at:'',cooperation_status:'active',status:'active',notes:'',
};
const blankPrice={name:'',unit:'',company_unit_price:'',mfec_share_type:'fixed',mfec_share_value:'',effective_from:date(),effective_to:'',notes:''};
const blankContract={contract_number:'',signed_at:'',effective_from:date(),effective_to:'',notes:''};

function Field({label,children,className='',error}:{label:string;children:React.ReactNode;className?:string;error?:string}){
  return <div className={className}>
    <Label className="mb-1 block">{label}</Label>
    {children}
    {error?<p className="text-xs text-red-600 mt-1">{error}</p>:null}
  </div>;
}

function slugifyArabic(value:string){
  const ascii=value.trim().toLowerCase().replace(/[^a-z0-9]+/g,'_').replace(/^_|_$/g,'');
  return ascii || `custom_${Date.now()}`;
}

async function resolveServiceTypeId(services:ServiceType[],activityCode:ActivityCode,otherActivity:string){
  const ensured=(await financialErpApi.serviceTypes(true)).items;
  if(activityCode!=='other'){
    const found=ensured.find(s=>s.code===activityCode)||ensured.find(s=>s.name===ACTIVITY_OPTIONS.find(o=>o.code===activityCode)?.label);
    if(!found)throw new Error('تعذر تجهيز نوع الخدمة المحدد. أعد تحميل الصفحة ثم حاول مجددًا.');
    return {serviceTypeId:found.id,services:ensured};
  }
  const customName=otherActivity.trim();
  if(customName.length<2)throw new Error('اكتب نوع النشاط عند اختيار «أخرى».');
  const existing=ensured.find(s=>s.name===customName);
  if(existing)return {serviceTypeId:existing.id,services:ensured};
  const created=await financialErpApi.createServiceType({name:customName,code:`other_${slugifyArabic(customName)}`.slice(0,64),is_active:true});
  return {serviceTypeId:created.id,services:[...ensured,created as ServiceType]};
}

export function CompaniesPage({companies,services,reloadCompanies,can,notify,success}:Common){
  const [localServices,setLocalServices]=useState(services);
  const [search,setSearch]=useState('');
  const [status,setStatus]=useState('all');
  const [createOpen,setCreateOpen]=useState(false);
  const [editingId,setEditingId]=useState<number|undefined>();
  const [form,setForm]=useState({...blankCompany});
  const [errors,setErrors]=useState<Record<string,string>>({});
  const [savingCompany,setSavingCompany]=useState(false);
  const [expanded,setExpanded]=useState<string>('');
  const [details,setDetails]=useState<Record<number,{
    pricing:PricingItem[];attachments:Attachment[];contract:typeof blankContract;loading:boolean;
  }>>({});
  const [priceOpen,setPriceOpen]=useState(false);
  const [priceCompanyId,setPriceCompanyId]=useState<number>();
  const [editPrice,setEditPrice]=useState<PricingItem>();
  const [priceForm,setPriceForm]=useState({...blankPrice});
  const [priceHistory,setPriceHistory]=useState<any[]>([]);
  const [historyOpen,setHistoryOpen]=useState(false);
  const [savingPrice,setSavingPrice]=useState(false);
  const [savingContract,setSavingContract]=useState<number|null>(null);

  useEffect(()=>{setLocalServices(services)},[services]);
  useEffect(()=>{(async()=>{try{setLocalServices((await financialErpApi.serviceTypes(true)).items)}catch(e){notify(e)}})()},[]);

  const filtered=useMemo(()=>companies.filter(x=>(status==='all'||x.cooperation_status===status)&&
    [x.name,x.service_type_name,x.owner_name,x.mobile].some(v=>String(v||'').toLowerCase().includes(search.toLowerCase()))),
  [companies,search,status]);

  const validateCompany=()=>{
    const next:Record<string,string>={};
    if(form.name.trim().length<2)next.name='اسم الشركة مطلوب ويجب أن يتكون من حرفين على الأقل';
    if(!form.activity_code)next.activity_code='اختر نوع الخدمة / النشاط';
    if(form.activity_code==='other'&&form.other_activity.trim().length<2)next.other_activity='اكتب نوع النشاط عند اختيار «أخرى»';
    if(!form.owner_name.trim())next.owner_name='اسم صاحب الشركة مطلوب';
    if(!form.mobile.trim())next.mobile='رقم الهاتف مطلوب';
    if(!form.address.trim())next.address='عنوان الشركة مطلوب';
    if(!form.cooperation_started_at)next.cooperation_started_at='تاريخ التعاون مطلوب';
    setErrors(next);
    return Object.keys(next).length===0;
  };

  const openCreate=()=>{setEditingId(undefined);setForm({...blankCompany});setErrors({});setCreateOpen(true)};

  const saveCompany=async()=>{
    if(!validateCompany()){notify(new Error('أكمل الحقول الإلزامية الموضحة تحت النموذج'));return}
    const allowed=editingId
      ?(can('financial.companies.edit')||can('manage_companies_contracts'))
      :(can('financial.companies.create')||can('manage_companies_contracts'));
    if(!allowed){notify(new Error(editingId?'ليست لديك صلاحية تعديل الشركة':'ليست لديك صلاحية إضافة شركة'));return}
    setSavingCompany(true);
    try{
      const {serviceTypeId,services:ensured}=await resolveServiceTypeId(localServices,form.activity_code as ActivityCode,form.other_activity);
      setLocalServices(ensured);
      const payload={
        name:form.name.trim(),
        service_type_id:serviceTypeId,
        owner_name:form.owner_name.trim(),
        mobile:form.mobile.trim(),
        address:form.address.trim(),
        contact_info:form.contact_info.trim()||null,
        cooperation_started_at:form.cooperation_started_at,
        cooperation_status:form.cooperation_status,
        status:form.status,
        notes:form.notes.trim()||null,
        contract_start:form.cooperation_started_at,
      };
      const saved=await financialErpApi.saveCompany(payload,editingId);
      const reloaded=(await financialErpApi.companies()).items;
      const persisted=reloaded.find(c=>c.id===saved.id);
      if(!persisted)throw new Error('أعاد الخادم نجاح الحفظ لكن الشركة لم تظهر بعد إعادة التحميل');
      await reloadCompanies();
      setCreateOpen(false);
      setEditingId(undefined);
      setExpanded(String(saved.id));
      success(editingId?`تم تحديث الشركة «${persisted.name}» بنجاح`:`تم حفظ الشركة «${persisted.name}» بنجاح`);
      await loadDetails(saved.id);
    }catch(e){notify(e)}finally{setSavingCompany(false)}
  };

  const loadDetails=async(companyId:number)=>{
    setDetails(prev=>({...prev,[companyId]:{...(prev[companyId]||{pricing:[],attachments:[],contract:{...blankContract}}),loading:true}}));
    try{
      const [pricing,attachments,contract]=await Promise.all([
        financialErpApi.pricingItems(companyId,{includeInactive:true,forManagement:true}),
        financialErpApi.companyAttachments(companyId),
        financialErpApi.primaryContract(companyId),
      ]);
      setDetails(prev=>({...prev,[companyId]:{
        loading:false,
        pricing:pricing.items,
        attachments:attachments.items,
        contract:{
          contract_number:contract.contract_number||'',
          signed_at:contract.signed_at||'',
          effective_from:contract.effective_from||date(),
          effective_to:contract.effective_to||'',
          notes:contract.notes||'',
        },
      }}));
    }catch(e){
      setDetails(prev=>({...prev,[companyId]:{...(prev[companyId]||{pricing:[],attachments:[],contract:{...blankContract}}),loading:false}}));
      notify(e);
    }
  };

  const onAccordionChange=async(value:string)=>{
    setExpanded(value);
    if(value)await loadDetails(Number(value));
  };

  const saveContract=async(companyId:number)=>{
    const contract=details[companyId]?.contract;
    if(!contract?.effective_from){notify(new Error('تاريخ بداية العقد مطلوب'));return}
    setSavingContract(companyId);
    try{
      await financialErpApi.savePrimaryContract(companyId,{
        contract_number:contract.contract_number||null,
        signed_at:contract.signed_at||null,
        effective_from:contract.effective_from,
        effective_to:contract.effective_to||null,
        notes:contract.notes||null,
      });
      await loadDetails(companyId);
      success('تم حفظ بيانات العقد الأساسي');
    }catch(e){notify(e)}finally{setSavingContract(null)}
  };

  const uploadAttachment=async(companyId:number,file:File,replacedId?:number)=>{
    try{
      const up=await financialErpApi.upload('contracts',file);
      await financialErpApi.addCompanyAttachment(companyId,{
        ...up,original_filename:file.name,mime_type:file.type||'application/octet-stream',
        size_bytes:file.size,document_type:'contract',replaced_id:replacedId||null,
      });
      await loadDetails(companyId);
      success(replacedId?'تم استبدال المرفق':'تم رفع مرفق العقد');
    }catch(e){notify(e)}
  };

  const openPriceDialog=(companyId:number,item?:PricingItem)=>{
    setPriceCompanyId(companyId);
    setEditPrice(item);
    setPriceForm(item?{
      ...blankPrice,
      name:item.name,
      unit:item.unit,
      company_unit_price:String(item.current_version?.company_unit_price??''),
      mfec_share_type:item.current_version?.mfec_share_type||'fixed',
      mfec_share_value:String(item.current_version?.mfec_share_value??''),
      effective_from:date(),
      effective_to:'',
      notes:item.notes||'',
    }:{...blankPrice});
    setPriceOpen(true);
  };

  const savePrice=async()=>{
    if(!priceCompanyId)return;
    if(!editPrice&&!priceForm.name.trim()){notify(new Error('اسم الفقرة مطلوب'));return}
    if(!editPrice&&!priceForm.unit.trim()){notify(new Error('الوحدة مطلوبة'));return}
    if(priceForm.company_unit_price===''||Number.isNaN(Number(priceForm.company_unit_price))){notify(new Error('سعر العميل مطلوب'));return}
    if(priceForm.mfec_share_value===''||Number.isNaN(Number(priceForm.mfec_share_value))){notify(new Error('قيمة حصة التجمع مطلوبة'));return}
    if(!priceForm.effective_from){notify(new Error('تاريخ بدء السعر مطلوب'));return}
    setSavingPrice(true);
    try{
      const payload={
        name:priceForm.name.trim(),
        unit:priceForm.unit.trim(),
        company_unit_price:Number(priceForm.company_unit_price),
        mfec_share_type:priceForm.mfec_share_type,
        mfec_share_value:Number(priceForm.mfec_share_value),
        effective_from:priceForm.effective_from,
        effective_to:priceForm.effective_to||null,
        notes:priceForm.notes.trim()||null,
      };
      if(editPrice)await financialErpApi.createPricingVersion(editPrice.id,{...payload,name:editPrice.name,unit:editPrice.unit});
      else await financialErpApi.createPricingItem(priceCompanyId,payload);
      await loadDetails(priceCompanyId);
      setPriceOpen(false);
      success(editPrice?'تم إنشاء نسخة سعر جديدة دون تعديل النسخ السابقة':'تمت إضافة فقرة التحاسب');
    }catch(e){notify(e)}finally{setSavingPrice(false)}
  };

  const showHistory=async(item:PricingItem)=>{
    try{
      setEditPrice(item);
      setPriceHistory((await financialErpApi.pricingVersions(item.id)).items);
      setHistoryOpen(true);
    }catch(e){notify(e)}
  };

  const canCreate=can('financial.companies.create')||can('manage_companies_contracts');
  const canEdit=can('financial.companies.edit')||can('manage_companies_contracts');
  const canContracts=can('financial.contracts.manage')||can('manage_companies_contracts');
  const canPricing=can('financial.pricing.manage')||can('manage_companies_contracts');

  return <div className="space-y-4">
    <PageTitle
      title="الشركات والعقود"
      description="إنشاء الشركة أولًا، ثم إدارة العقد الأساسي وفقرات التحاسب من تفاصيل كل شركة."
      actions={canCreate&&<Button type="button" onClick={openCreate}><Plus className="w-4 h-4 ml-2"/>شركة جديدة</Button>}
    />

    <Card><CardContent className="p-3 flex gap-2 flex-wrap">
      <SearchBox value={search} onChange={setSearch} placeholder="اسم الشركة، المالك، الهاتف..."/>
      <select className="h-10 border rounded-md px-3 bg-white" value={status} onChange={e=>setStatus(e.target.value)}>
        <option value="all">كل حالات التعاون</option>
        <option value="active">فعال</option>
        <option value="suspended">موقوف</option>
        <option value="ended">منتهي</option>
      </select>
      <span className="text-sm text-slate-500 self-center">{filtered.length} شركة</span>
    </CardContent></Card>

    {!filtered.length&&<Empty title="لا توجد شركات" description="أضف شركة جديدة من الزر أعلاه."/>}

    <Accordion type="single" collapsible value={expanded} onValueChange={value=>void onAccordionChange(value)} className="space-y-3">
      {filtered.map(company=>{
        const detail=details[company.id];
        return <AccordionItem key={company.id} value={String(company.id)} className="border rounded-xl bg-white px-4">
          <AccordionTrigger className="hover:no-underline py-4">
            <div className="flex flex-1 flex-col md:flex-row md:items-center md:justify-between gap-2 text-right">
              <div>
                <b className="text-base">{company.name}</b>
                <small className="block text-slate-500">{company.service_type_name} · {company.owner_name||'بدون مالك'} · {company.mobile||'-'}</small>
              </div>
              <div className="flex items-center gap-2 justify-end">
                <StatusBadge value={company.cooperation_status}/>
                <StatusBadge value={company.status}/>
                <span className="text-xs text-slate-500 inline-flex items-center"><ChevronDown className="w-4 h-4 ml-1"/>تفاصيل الشركة</span>
              </div>
            </div>
          </AccordionTrigger>
          <AccordionContent className="pb-5 space-y-4">
            {detail?.loading&&<p className="text-sm text-slate-500">جاري تحميل تفاصيل الشركة...</p>}
            {!detail?.loading&&<>
              <Card>
                <CardHeader className="pb-2"><CardTitle className="text-base">بيانات الشركة</CardTitle></CardHeader>
                <CardContent className="grid md:grid-cols-3 gap-3 text-sm">
                  <div><small className="text-slate-500 block">نوع الخدمة</small><b>{company.service_type_name}</b></div>
                  <div><small className="text-slate-500 block">صاحب الشركة</small><b>{company.owner_name||'-'}</b></div>
                  <div><small className="text-slate-500 block">الهاتف</small><b>{company.mobile||'-'}</b></div>
                  <div className="md:col-span-2"><small className="text-slate-500 block">العنوان</small><b>{company.address||'-'}</b></div>
                  <div><small className="text-slate-500 block">تاريخ التعاون</small><b>{company.cooperation_started_at||'-'}</b></div>
                  <div className="md:col-span-3"><small className="text-slate-500 block">معلومات الاتصال</small><b>{company.contact_info||'-'}</b></div>
                  <div className="md:col-span-3"><small className="text-slate-500 block">ملاحظات</small><b>{company.notes||'-'}</b></div>
                  {canEdit&&<div className="md:col-span-3"><Button type="button" variant="outline" size="sm" onClick={()=>{
                    const code=(ACTIVITY_OPTIONS.find(o=>o.label===company.service_type_name)?.code
                      ||localServices.find(s=>s.id===company.service_type_id)?.code
                      ||'other') as ActivityCode;
                    setEditingId(company.id);
                    setForm({
                      name:company.name,
                      activity_code:ACTIVITY_OPTIONS.some(o=>o.code===code)?code:'other',
                      other_activity:ACTIVITY_OPTIONS.some(o=>o.label===company.service_type_name)?'':(company.service_type_name||''),
                      owner_name:company.owner_name||'',
                      address:company.address||'',
                      mobile:company.mobile||'',
                      contact_info:company.contact_info||'',
                      cooperation_started_at:company.cooperation_started_at||'',
                      cooperation_status:company.cooperation_status||'active',
                      status:company.status||'active',
                      notes:company.notes||'',
                    });
                    setErrors({});
                    setCreateOpen(true);
                  }}>تعديل بيانات الشركة</Button></div>}
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2 flex-row items-center justify-between space-y-0">
                  <CardTitle className="text-base">العقد الأساسي مع مسار الفهد</CardTitle>
                  {canContracts&&<FileButton label="رفع مرفق" onFile={file=>uploadAttachment(company.id,file)}/>}
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="grid md:grid-cols-3 gap-3">
                    <Field label="رقم العقد"><Input value={detail?.contract.contract_number||''} onChange={e=>setDetails(prev=>({...prev,[company.id]:{...prev[company.id],contract:{...prev[company.id].contract,contract_number:e.target.value}}}))}/></Field>
                    <Field label="تاريخ التوقيع"><SafeDateInput value={detail?.contract.signed_at||''} onChange={e=>setDetails(prev=>({...prev,[company.id]:{...prev[company.id],contract:{...prev[company.id].contract,signed_at:e.target.value}}}))}/></Field>
                    <Field label="تاريخ بداية العقد *"><SafeDateInput value={detail?.contract.effective_from||''} onChange={e=>setDetails(prev=>({...prev,[company.id]:{...prev[company.id],contract:{...prev[company.id].contract,effective_from:e.target.value}}}))}/></Field>
                    <Field label="تاريخ النهاية (اختياري)"><SafeDateInput value={detail?.contract.effective_to||''} onChange={e=>setDetails(prev=>({...prev,[company.id]:{...prev[company.id],contract:{...prev[company.id].contract,effective_to:e.target.value}}}))}/></Field>
                    <Field label="ملاحظات العقد" className="md:col-span-2"><Textarea value={detail?.contract.notes||''} onChange={e=>setDetails(prev=>({...prev,[company.id]:{...prev[company.id],contract:{...prev[company.id].contract,notes:e.target.value}}}))}/></Field>
                  </div>
                  {canContracts&&<Button type="button" disabled={savingContract===company.id} onClick={()=>void saveContract(company.id)}>{savingContract===company.id?'جاري الحفظ...':'حفظ بيانات العقد'}</Button>}
                  <div className="space-y-2">
                    <h4 className="font-semibold text-sm">مرفقات العقد (PDF / Word / Excel / صور)</h4>
                    {!detail?.attachments?.length&&<Empty title="لا توجد مرفقات" description="يمكن رفع أكثر من ملف للعقد وملف الأسعار."/>}
                    {detail?.attachments?.map(a=><div key={a.id} className="border rounded-lg p-2 flex justify-between items-center gap-2">
                      <span className="text-sm"><FileText className="w-4 h-4 inline ml-2"/>{a.original_filename}<small className="block text-slate-500">{a.uploaded_at||''}</small></span>
                      <div className="flex items-center">
                        <Button type="button" size="icon" variant="ghost" onClick={()=>financialErpApi.openDocument(a.object_key)}><Eye className="w-4 h-4"/></Button>
                        <Button type="button" size="icon" variant="ghost" onClick={()=>financialErpApi.openDocument(a.object_key,a.original_filename)}><Download className="w-4 h-4"/></Button>
                        {canContracts&&<FileButton label="استبدال" onFile={file=>uploadAttachment(company.id,file,a.id)}/>}
                        {canContracts&&<Button type="button" size="icon" variant="ghost" onClick={async()=>{await financialErpApi.deleteCompanyAttachment(company.id,a.id);await loadDetails(company.id);success('تم حذف المرفق منطقيًا')}}><Trash2 className="w-4 h-4 text-red-600"/></Button>}
                      </div>
                    </div>)}
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2 flex-row items-center justify-between space-y-0">
                  <CardTitle className="text-base">فقرات التحاسب والأسعار</CardTitle>
                  {canPricing&&<Button type="button" size="sm" onClick={()=>openPriceDialog(company.id)}><Plus className="w-4 h-4 ml-1"/>إضافة فقرة</Button>}
                </CardHeader>
                <CardContent>
                  <CompactTable headers={['الفقرة','الوحدة','سعر العميل','نوع حصة MFEC','قيمة الحصة','بدء السعر','النهاية','الحالة','']}>
                    {(detail?.pricing||[]).map(p=>{
                      const v=p.current_version;
                      return <tr key={p.id} className="border-t">
                        <td className="p-2 font-medium">{p.name}</td>
                        <td>{p.unit}</td>
                        <td>{money(v?.company_unit_price)}</td>
                        <td>{v?.mfec_share_type==='percentage'?'نسبة':'مبلغ ثابت'}</td>
                        <td>{v?.mfec_share_type==='percentage'?`${v.mfec_share_value}%`:money(v?.mfec_share_value)}</td>
                        <td>{v?.effective_from||'-'}</td>
                        <td>{v?.effective_to||'مستمر'}</td>
                        <td><StatusBadge value={p.is_active?'active':'inactive'}/></td>
                        <td className="p-2">
                          <div className="flex gap-1">
                            {canPricing&&<Button type="button" size="sm" variant="ghost" title="تعديل عبر نسخة جديدة" onClick={()=>openPriceDialog(company.id,p)}><Edit3 className="w-4 h-4"/></Button>}
                            {canPricing&&<Button type="button" size="sm" variant="ghost" title="تاريخ الأسعار" onClick={()=>void showHistory(p)}><History className="w-4 h-4"/></Button>}
                            {canPricing&&<Button type="button" size="sm" variant="outline" onClick={async()=>{
                              await financialErpApi.setPricingItemStatus(p.id,!p.is_active);
                              await loadDetails(company.id);
                              success(p.is_active?'تم تعطيل الفقرة':'تم تفعيل الفقرة');
                            }}>{p.is_active?'تعطيل':'تفعيل'}</Button>}
                          </div>
                        </td>
                      </tr>;
                    })}
                    {!detail?.pricing?.length&&<tr><td colSpan={9}><Empty title="لا توجد فقرات" description="أضف فقرة مثل كارتون أو كيلو."/></td></tr>}
                  </CompactTable>
                </CardContent>
              </Card>
            </>}
          </AccordionContent>
        </AccordionItem>;
      })}
    </Accordion>

    <FormDialog open={createOpen} onOpenChange={(open)=>{setCreateOpen(open);if(!open)setEditingId(undefined)}} title={editingId?'تعديل بيانات الشركة':'إضافة شركة جديدة'} className="max-w-3xl">
      <div className="grid md:grid-cols-2 gap-3">
        <Field label="اسم الشركة *" error={errors.name}><Input value={form.name} onChange={e=>setForm({...form,name:e.target.value})}/></Field>
        <Field label="نوع الخدمة / النشاط *" error={errors.activity_code}>
          <select className="w-full h-10 border rounded-md px-3 bg-white" value={form.activity_code} onChange={e=>setForm({...form,activity_code:e.target.value as ActivityCode|'',other_activity:e.target.value==='other'?form.other_activity:''})}>
            <option value="">اختر نوع الخدمة</option>
            {ACTIVITY_OPTIONS.map(o=><option key={o.code} value={o.code}>{o.label}</option>)}
          </select>
        </Field>
        {form.activity_code==='other'&&<Field label="اكتب نوع النشاط *" className="md:col-span-2" error={errors.other_activity}><Input value={form.other_activity} onChange={e=>setForm({...form,other_activity:e.target.value})} placeholder="مثال: بوابات دفع"/></Field>}
        <Field label="اسم صاحب الشركة *" error={errors.owner_name}><Input value={form.owner_name} onChange={e=>setForm({...form,owner_name:e.target.value})}/></Field>
        <Field label="الهاتف *" error={errors.mobile}><Input value={form.mobile} onChange={e=>setForm({...form,mobile:e.target.value})}/></Field>
        <Field label="العنوان *" className="md:col-span-2" error={errors.address}><Input value={form.address} onChange={e=>setForm({...form,address:e.target.value})}/></Field>
        <Field label="تاريخ التعاون *" error={errors.cooperation_started_at}><SafeDateInput value={form.cooperation_started_at} onChange={e=>setForm({...form,cooperation_started_at:e.target.value})}/></Field>
        <Field label="حالة التعاون">
          <select className="w-full h-10 border rounded-md px-3" value={form.cooperation_status} onChange={e=>setForm({...form,cooperation_status:e.target.value})}>
            <option value="active">فعال</option>
            <option value="suspended">موقوف</option>
            <option value="ended">منتهي</option>
          </select>
        </Field>
        <Field label="الحالة النظامية">
          <select className="w-full h-10 border rounded-md px-3" value={form.status} onChange={e=>setForm({...form,status:e.target.value})}>
            <option value="active">فعال</option>
            <option value="inactive">غير فعال</option>
          </select>
        </Field>
        <Field label="معلومات الاتصال" className="md:col-span-2"><Textarea value={form.contact_info} onChange={e=>setForm({...form,contact_info:e.target.value})} placeholder="بريد، واتساب، شخص تواصل..."/></Field>
        <Field label="ملاحظات" className="md:col-span-2"><Textarea value={form.notes} onChange={e=>setForm({...form,notes:e.target.value})}/></Field>
      </div>
      <div className="flex justify-end gap-2 pt-2">
        <Button type="button" variant="outline" onClick={()=>setCreateOpen(false)}>إلغاء</Button>
        <Button type="button" disabled={savingCompany} onClick={()=>void saveCompany()}>{savingCompany?'جاري الحفظ...':'حفظ بيانات الشركة'}</Button>
      </div>
    </FormDialog>

    <FormDialog open={priceOpen} onOpenChange={setPriceOpen} title={editPrice?`نسخة سعر جديدة — ${editPrice.name}`:'إضافة فقرة تحاسب'}>
      <div className="grid md:grid-cols-2 gap-3">
        {!editPrice&&<>
          <Field label="اسم الفقرة *"><Input value={priceForm.name} onChange={e=>setPriceForm({...priceForm,name:e.target.value})} placeholder="كارتون / كيلو"/></Field>
          <Field label="الوحدة *"><Input value={priceForm.unit} onChange={e=>setPriceForm({...priceForm,unit:e.target.value})} placeholder="كارتون / كغم"/></Field>
        </>}
        {editPrice&&<div className="md:col-span-2 text-sm bg-amber-50 border border-amber-200 rounded-md p-3">تعديل السعر ينشئ <b>نسخة جديدة</b> ولا يغيّر العمليات أو الأشهر السابقة.</div>}
        <Field label="سعر العميل *"><Input type="number" value={priceForm.company_unit_price} onChange={e=>setPriceForm({...priceForm,company_unit_price:e.target.value})}/></Field>
        <Field label="نوع حصة التجمع MFEC *">
          <select className="w-full h-10 border rounded-md px-3" value={priceForm.mfec_share_type} onChange={e=>setPriceForm({...priceForm,mfec_share_type:e.target.value})}>
            <option value="fixed">مبلغ ثابت</option>
            <option value="percentage">نسبة</option>
          </select>
        </Field>
        <Field label="قيمة حصة التجمع *"><Input type="number" value={priceForm.mfec_share_value} onChange={e=>setPriceForm({...priceForm,mfec_share_value:e.target.value})}/></Field>
        <Field label="تاريخ بدء السعر *"><SafeDateInput value={priceForm.effective_from} onChange={e=>setPriceForm({...priceForm,effective_from:e.target.value})}/></Field>
        <Field label="تاريخ انتهاء اختياري"><SafeDateInput value={priceForm.effective_to} onChange={e=>setPriceForm({...priceForm,effective_to:e.target.value})}/></Field>
        <Field label="ملاحظات" className="md:col-span-2"><Textarea value={priceForm.notes} onChange={e=>setPriceForm({...priceForm,notes:e.target.value})}/></Field>
      </div>
      {canPricing&&<Button type="button" disabled={savingPrice} onClick={()=>void savePrice()}>{savingPrice?'جاري الحفظ...':editPrice?'حفظ النسخة الجديدة':'حفظ الفقرة'}</Button>}
    </FormDialog>

    <FormDialog open={historyOpen} onOpenChange={setHistoryOpen} title={`تاريخ أسعار — ${editPrice?.name||''}`}>
      <CompactTable headers={['النسخة','من','إلى','سعر العميل','حصة MFEC']}>
        {priceHistory.map(v=><tr key={v.id} className="border-t">
          <td className="p-2">v{v.version}</td>
          <td>{v.effective_from}</td>
          <td>{v.effective_to||'مستمر'}</td>
          <td>{money(v.company_unit_price)}</td>
          <td>{v.mfec_share_type==='percentage'?`${v.mfec_share_value}%`:money(v.mfec_share_value)}</td>
        </tr>)}
        {!priceHistory.length&&<tr><td colSpan={5}><Empty title="لا يوجد تاريخ أسعار"/></td></tr>}
      </CompactTable>
    </FormDialog>
  </div>;
}

const blankAccount={member_id:'',company_id:'',registered_name:'',registered_phone:'',customer_code:'',customer_portal_url:'',started_at:date(),ended_at:'',status:'active',notes:'',is_active:true};
export function MemberLinksPage({companies,can,notify,success,finance}:Omit<Common,'services'|'reloadCompanies'>&{finance:boolean}){
  const [accounts,setAccounts]=useState<MemberAccount[]>([]);const [members,setMembers]=useState<MemberOption[]>([]);
  const [summaries,setSummaries]=useState<Record<number,AccountItem[]>>({});
  const [search,setSearch]=useState('');const [companyFilter,setCompanyFilter]=useState('');const [selected,setSelected]=useState<MemberAccount>();
  const [open,setOpen]=useState(false);const [form,setForm]=useState<any>(blankAccount);const [pricing,setPricing]=useState<PricingItem[]>([]);
  const [items,setItems]=useState<AccountItem[]>([]);const [annexes,setAnnexes]=useState<Attachment[]>([]);const [annexDate,setAnnexDate]=useState(date());
  const [customOverrides,setCustomOverrides]=useState<Record<number,boolean>>({});const [saving,setSaving]=useState(false);const [loadingPricing,setLoadingPricing]=useState(false);
  const selectedCompany=companies.find(company=>String(company.id)===String(form.company_id));
  const load=async()=>{try{const x=await financialErpApi.memberAccounts(financialErpApi.query({company_id:companyFilter,search}));setAccounts(x.items);
    const pairs=await Promise.all(x.items.map(async a=>[a.id,(await financialErpApi.accountItems(a.id)).items] as const));setSummaries(Object.fromEntries(pairs));
  }catch(e){notify(e)}};
  useEffect(()=>{load()},[companyFilter]);useEffect(()=>{if(can('financial.member_links.create'))financialErpApi.members().then(x=>setMembers(x.items)).catch(notify)},[]);
  const openAccount=async(account?:MemberAccount)=>{setSelected(account);setForm(account?{...blankAccount,...account,member_id:String(account.member_id),company_id:String(account.company_id)}:blankAccount);setOpen(true);
    if(account){const [p,i,a]=await Promise.all([financialErpApi.pricingItems(account.company_id),financialErpApi.accountItems(account.id),financialErpApi.annexes(account.id)]);setPricing(p.items);setItems(i.items);setCustomOverrides(Object.fromEntries(i.items.map(item=>[item.pricing_item_id,item.unit_price_override!=null||item.mfec_share_type_override!=null||item.mfec_share_value_override!=null])));setAnnexes(a.items)}else{setPricing([]);setItems([]);setCustomOverrides({});setAnnexes([])}};
  const chooseCompany=async(companyId:string)=>{setForm({...form,company_id:companyId});setPricing([]);setItems([]);setCustomOverrides({});if(!companyId)return;setLoadingPricing(true);try{const response=await financialErpApi.pricingItems(Number(companyId));setPricing(response.items)}catch(e){notify(e)}finally{setLoadingPricing(false)}};
  const save=async()=>{if(!form.member_id){notify(new Error('اختر العضو من سجل العضويات'));return}if(!form.company_id){notify(new Error('اختر الشركة'));return}if(!items.length){notify(new Error('اختر فقرة تحاسب واحدة على الأقل'));return}setSaving(true);try{
    const payload={...form,member_id:Number(form.member_id),company_id:Number(form.company_id),registered_name:form.registered_name?.trim()||null,registered_phone:form.registered_phone?.trim()||null,customer_code:form.customer_code?.trim()||null,
      customer_portal_url:form.customer_portal_url?.trim()||null,started_at:form.started_at||null,ended_at:form.ended_at||null,notes:form.notes?.trim()||null,
      default_unit_price_override:null,default_mfec_share_type_override:null,default_mfec_share_value_override:null,
      items:items.map(item=>({pricing_item_id:item.pricing_item_id,unit_price_override:customOverrides[item.pricing_item_id]?item.unit_price_override??null:null,
        mfec_share_type_override:customOverrides[item.pricing_item_id]?item.mfec_share_type_override||null:null,mfec_share_value_override:customOverrides[item.pricing_item_id]?item.mfec_share_value_override??null:null,is_active:true}))};
    const result=await financialErpApi.saveMemberAccount(payload);
    const [accountResponse,itemResponse]=await Promise.all([financialErpApi.memberAccounts(financialErpApi.query({member_id:payload.member_id,company_id:payload.company_id})),financialErpApi.accountItems(result.id)]);
    const fresh=accountResponse.items.find(account=>account.id===result.id);if(!fresh||itemResponse.items.length!==items.length)throw new Error('أعاد الخادم نجاح الحفظ لكن الحساب أو فقراته لم تظهر بعد إعادة التحميل');
    setSelected(fresh);setItems(itemResponse.items);setCustomOverrides(Object.fromEntries(itemResponse.items.map(item=>[item.pricing_item_id,item.unit_price_override!=null||item.mfec_share_type_override!=null||item.mfec_share_value_override!=null])));await load();
    success(`تم حفظ الحساب و${itemResponse.items.length} فقرة والتحقق من الأسعار الفعالة`);
  }catch(e){notify(e)}finally{setSaving(false)}};
  const toggleItem=(p:PricingItem,checked:boolean)=>setItems(old=>checked?[...old,{id:0,pricing_item_id:p.id,name:p.name,unit:p.unit,is_active:true,effective_unit_price:p.current_version?.company_unit_price,effective_mfec_share_type:p.current_version?.mfec_share_type,effective_mfec_share_value:p.current_version?.mfec_share_value}]:old.filter(x=>x.pricing_item_id!==p.id));
  const uploadAnnex=async(file:File,replacedId?:number)=>{if(!selected)return;try{const up=await financialErpApi.upload('annexes',file);await financialErpApi.addAnnex(selected.id,{...up,original_filename:file.name,mime_type:file.type,size_bytes:file.size,signed_at:annexDate||null,replaced_id:replacedId||null});setAnnexes((await financialErpApi.annexes(selected.id)).items);success('تم رفع ملحق الاتفاق الثلاثي')}catch(e){notify(e)}};
  return <div className="space-y-4">
    <PageTitle title="ارتباطات الأعضاء" description="حسابات الأعضاء لدى الشركات، الفقرات الفعالة، الاستثناءات والملحق الثلاثي." actions={can('financial.member_links.create')&&<Button onClick={()=>openAccount()}><Plus className="w-4 h-4 ml-2"/>ارتباط جديد</Button>}/>
    <Card><CardContent className="p-3 flex gap-2 flex-wrap"><SearchBox value={search} onChange={setSearch} placeholder="العضو، رقم العضوية، كود العميل..."/><Button variant="outline" onClick={load}>بحث</Button><select className="h-10 border rounded-md px-3" value={companyFilter} onChange={e=>setCompanyFilter(e.target.value)}><option value="">كل الشركات</option>{companies.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></CardContent></Card>
    <CompactTable headers={['العضو / النشاط','المحافظة','الشركة / الخدمة','الفقرات الفعالة','بيانات التسجيل','بدء الارتباط','الحالة','الرابط','']}>{accounts.map(a=><tr key={a.id} className="border-t"><td className="p-3"><b>{a.member_name}</b><small className="block">{a.business_name} · {a.membership_number}</small></td><td>{a.governorate}</td><td>{a.company_name}<small className="block">{a.service_type_name}</small></td><td>{summaries[a.id]?.map(x=><div key={x.id}>{x.name} ({x.unit}){finance&&<small> · {money(x.effective_unit_price)} / {x.effective_mfec_share_type==='percentage'?`${x.effective_mfec_share_value}%`:money(x.effective_mfec_share_value)}</small>}</div>)||'-'}</td><td>{a.registered_name||'-'}<small className="block">{a.registered_phone} · {a.customer_code}</small></td><td>{a.started_at||'-'}</td><td><StatusBadge value={a.status}/></td><td>{a.customer_portal_url&&<Button size="sm" variant="outline" onClick={()=>window.open(a.customer_portal_url,'_blank','noopener,noreferrer')}><ExternalLink className="w-4 h-4"/></Button>}</td><td><Button size="sm" variant="ghost" onClick={()=>openAccount(a)}><Edit3 className="w-4 h-4"/></Button></td></tr>)}</CompactTable>
    <FormDialog open={open} onOpenChange={setOpen} title={selected?`حساب ${selected.member_name} لدى ${selected.company_name}`:'ارتباط عضو بشركة'} className="max-w-5xl">
      <div className="grid md:grid-cols-3 gap-3"><Field label="العضو"><select disabled={!!selected} className="w-full h-10 border rounded-md px-3" value={form.member_id} onChange={e=>setForm({...form,member_id:e.target.value})}><option value="">اختر</option>{members.map(m=><option key={m.id} value={m.id}>{m.membership_number} · {m.member_name} · {m.business_name}</option>)}</select></Field>
        <Field label="الشركة"><select disabled={!!selected} className="w-full h-10 border rounded-md px-3" value={form.company_id} onChange={e=>void chooseCompany(e.target.value)}><option value="">اختر</option>{companies.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
        <Field label="نوع الخدمة"><Input readOnly className="bg-slate-50" value={selectedCompany?.service_type_name||''} placeholder="يظهر تلقائياً من الشركة"/></Field>
        <Field label="الحالة"><select className="w-full h-10 border rounded-md px-3" value={form.status} onChange={e=>setForm({...form,status:e.target.value,is_active:e.target.value==='active'})}><option value="active">فعال</option><option value="inactive">غير فعال</option><option value="suspended">معلق</option></select></Field>
        <Field label="الاسم المسجل"><Input value={form.registered_name||''} onChange={e=>setForm({...form,registered_name:e.target.value})}/></Field><Field label="الهاتف المسجل"><Input value={form.registered_phone||''} onChange={e=>setForm({...form,registered_phone:e.target.value})}/></Field><Field label="كود العميل"><Input value={form.customer_code||''} onChange={e=>setForm({...form,customer_code:e.target.value})}/></Field>
        <Field label="رابط بوابة العميل" className="md:col-span-2"><Input dir="ltr" value={form.customer_portal_url||''} onChange={e=>setForm({...form,customer_portal_url:e.target.value})}/></Field><Field label="تاريخ البدء"><SafeDateInput value={form.started_at||''} onChange={e=>setForm({...form,started_at:e.target.value})}/></Field>
        <Field label="ملاحظات" className="md:col-span-3"><Textarea value={form.notes||''} onChange={e=>setForm({...form,notes:e.target.value})}/></Field>
      </div>
      {!!form.company_id&&<div className="border-t pt-4 space-y-3"><div><h3 className="font-bold">فقرات التحاسب النشطة</h3><p className="text-sm text-slate-500">اختر الفقرات؛ سعر الشركة وحصة MFEC يطبقان تلقائياً ما لم تفعّل استثناءً.</p></div>
        {loadingPricing&&<p className="text-sm text-slate-500">جاري تحميل أسعار الشركة...</p>}
        {!loadingPricing&&!pricing.length&&<Empty title="لا توجد فقرات تحاسب نشطة" description="أضف فقرة وسعراً فعالاً إلى الشركة أولاً."/>}
        {pricing.map(p=>{const item=items.find(x=>x.pricing_item_id===p.id);const version=p.current_version;const custom=!!customOverrides[p.id];return <div key={p.id} className={`border rounded-lg p-3 space-y-3 ${item?'border-blue-300 bg-blue-50/30':''}`}>
          <div className="flex gap-3 items-start"><Checkbox aria-label={`اختيار ${p.name}`} checked={!!item} onCheckedChange={v=>toggleItem(p,!!v)}/><div className="grid sm:grid-cols-4 gap-x-6 gap-y-1 flex-1 text-sm"><span><small className="block text-slate-500">الفقرة</small><b>{p.name}</b></span><span><small className="block text-slate-500">الوحدة</small>{p.unit}</span><span><small className="block text-slate-500">سعر الشركة</small>{money(version?.company_unit_price)}</span><span><small className="block text-slate-500">حصة MFEC</small>{version?.mfec_share_type==='percentage'?`${version.mfec_share_value}%`:money(version?.mfec_share_value)} · {version?.mfec_share_type==='percentage'?'نسبة':'ثابت'}</span></div></div>
          {item&&<><label className="flex items-center gap-2 text-sm font-medium"><Checkbox checked={custom} onCheckedChange={value=>setCustomOverrides(old=>({...old,[p.id]:!!value}))}/>استخدام سعر/حصة خاصة لهذا العضو</label>
            {custom&&<div className="grid md:grid-cols-3 gap-2"><Field label="سعر الوحدة الخاص (اختياري)"><Input type="number" placeholder={String(version?.company_unit_price??'')} value={item.unit_price_override??''} onChange={e=>setItems(xs=>xs.map(x=>x.pricing_item_id===p.id?{...x,unit_price_override:e.target.value===''?undefined:Number(e.target.value)}:x))}/></Field><Field label="نوع الحصة الخاصة (اختياري)"><select className="h-10 w-full border rounded-md px-2" value={item.mfec_share_type_override||''} onChange={e=>setItems(xs=>xs.map(x=>x.pricing_item_id===p.id?{...x,mfec_share_type_override:(e.target.value||undefined) as any}:x))}><option value="">حصة الشركة</option><option value="fixed">ثابت</option><option value="percentage">نسبة</option></select></Field><Field label="قيمة الحصة الخاصة (اختياري)"><Input type="number" placeholder={String(version?.mfec_share_value??'')} value={item.mfec_share_value_override??''} onChange={e=>setItems(xs=>xs.map(x=>x.pricing_item_id===p.id?{...x,mfec_share_value_override:e.target.value===''?undefined:Number(e.target.value)}:x))}/></Field></div>}</>}
        </div>})}</div>}
      {can(selected?'financial.member_links.edit':'financial.member_links.create')&&<Button type="button" disabled={saving||loadingPricing} onClick={save}>{saving?'جاري الحفظ والتحقق...':'حفظ الحساب والفقرات'}</Button>}
      {selected&&<div className="border-t pt-4 space-y-2"><div className="flex justify-between items-end gap-2"><h3 className="font-bold">ملحق الاتفاق الثلاثي</h3>{can('financial.annexes.manage')&&<div className="flex items-end gap-2"><Field label="تاريخ التوقيع"><SafeDateInput className="w-40" value={annexDate} onChange={e=>setAnnexDate(e.target.value)}/></Field><FileButton onFile={uploadAnnex}/></div>}</div>{annexes.map(a=><div key={a.id} className="flex justify-between border rounded p-2"><span>{a.original_filename}<small className="block text-slate-500">{a.signed_at?`موقع في ${a.signed_at}`:'دون تاريخ توقيع'}</small></span><div className="flex"><Button size="icon" variant="ghost" onClick={()=>financialErpApi.openDocument(a.object_key)}><Eye className="w-4 h-4"/></Button>{can('financial.annexes.manage')&&<FileButton label="استبدال" onFile={file=>uploadAnnex(file,a.id)}/>} {can('financial.annexes.manage')&&<Button size="icon" variant="ghost" onClick={async()=>{await financialErpApi.deleteAnnex(selected.id,a.id);setAnnexes((await financialErpApi.annexes(selected.id)).items)}}><Trash2 className="w-4 h-4 text-red-600"/></Button>}</div></div>)}</div>}
    </FormDialog>
  </div>;
}
