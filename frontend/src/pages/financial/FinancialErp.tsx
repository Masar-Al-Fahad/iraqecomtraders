import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { BarChart3, Building2, FileSpreadsheet, Link2, Receipt, Scale, Wallet } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useToast } from '@/hooks/use-toast';
import { useBrand } from '@/lib/brand';
import { financialErpApi } from '@/lib/financialErpApi';
import { ROUTES } from '@/lib/routes';
import type { Company, PermissionMap, ReportLine, StatementGridRow } from '@/types/financialErp';

const money=(v:number|undefined)=>`${Number(v||0).toLocaleString('ar-IQ')} د.ع`;
const today=new Date();
const sections=[
  ['dashboard','المؤشرات',BarChart3],['companies','الشركات والأسعار',Building2],
  ['links','ارتباطات الأعضاء',Link2],['monthly','الإدخال الشهري',FileSpreadsheet],
  ['settlements','التسويات',Scale],['revenues','الإيرادات',Wallet],
  ['reports','التقارير',Receipt],
] as const;

export default function FinancialErp(){
  const {brand,resolveAssetUrl}=useBrand(); const {toast}=useToast(); const nav=useNavigate(); const location=useLocation();
  const last=location.pathname.split('/').pop()||'financial';
  const section=last==='financial'?'dashboard':last;
  const [permissions,setPermissions]=useState<PermissionMap>({}); const [superAdmin,setSuperAdmin]=useState(false);
  const can=(p:string)=>superAdmin||!!permissions[p];
  const [companies,setCompanies]=useState<Company[]>([]); const [companyId,setCompanyId]=useState(0);
  const [year,setYear]=useState(today.getFullYear()); const [month,setMonth]=useState(today.getMonth()+1);
  const [dashboard,setDashboard]=useState<any>(); const [grid,setGrid]=useState<StatementGridRow[]>([]);
  const [statementId,setStatementId]=useState<number|null>(null); const [statementStatus,setStatementStatus]=useState('draft');
  const [report,setReport]=useState<ReportLine[]>([]); const [totals,setTotals]=useState<Record<string,number>>({});
  const [selected,setSelected]=useState<number[]>([]); const [revenues,setRevenues]=useState<any[]>([]); const [settlements,setSettlements]=useState<any[]>([]);
  const [busy,setBusy]=useState(false);
  const [revenueForm,setRevenueForm]=useState({receipt_number:'',amount:'',received_at:new Date().toISOString().slice(0,10),receipt_method:'نقدي',description:''});
  const [pricing,setPricing]=useState<any[]>([]); const [pricingForm,setPricingForm]=useState({name:'',unit:'طلب',company_unit_price:'',mfec_share_type:'fixed',mfec_share_value:'',effective_from:new Date().toISOString().slice(0,10)});
  const notify=(e:any)=>toast({title:'تعذر إكمال العملية',description:e?.message||'خطأ غير متوقع',variant:'destructive'});
  const reportQuery=useMemo(()=>{
    const q=new URLSearchParams({accounting_year:String(year),accounting_month:String(month)});
    if(companyId)q.set('company_id',String(companyId)); selected.forEach(id=>q.append('selected_ids',String(id))); return q.toString();
  },[year,month,companyId,selected]);

  useEffect(()=>{(async()=>{try{
    const [a,c]=await Promise.all([financialErpApi.access(),financialErpApi.companies()]);
    setPermissions(a.permissions);setSuperAdmin(a.is_super_admin);setCompanies(c.items);if(c.items[0])setCompanyId(c.items[0].id);
  }catch(e){notify(e)}})()},[]);
  useEffect(()=>{if(!companyId)return; if(section==='dashboard'&&can('financial.dashboard.view'))financialErpApi.dashboard(year,month).then(setDashboard).catch(notify);
    if(section==='companies')financialErpApi.pricingItems(companyId).then(x=>setPricing(x.items)).catch(notify);
    if(section==='revenues')financialErpApi.revenues().then(x=>setRevenues(x.items)).catch(notify);
    if(section==='settlements')financialErpApi.settlements().then(x=>setSettlements(x.items)).catch(notify);
  },[section,companyId,year,month,permissions,superAdmin]);

  const loadGrid=async()=>{setBusy(true);try{const x=await financialErpApi.statementGrid(companyId,year,month);setGrid(x.items);setStatementId(x.statement_id);setStatementStatus(x.status)}catch(e){notify(e)}finally{setBusy(false)}};
  const saveGrid=async()=>{setBusy(true);try{const x=await financialErpApi.saveStatement({company_id:companyId,accounting_year:year,accounting_month:month,lines:grid.map(r=>({account_item_id:r.account_item_id,quantity:r.quantity,excluded:r.excluded}))});setStatementId(x.statement_id);toast({title:`تم حفظ ${x.saved} بندًا`})}catch(e){notify(e)}finally{setBusy(false)}};
  const loadReport=async()=>{try{const x=await financialErpApi.report(reportQuery);setReport(x.items);setTotals(x.totals)}catch(e){notify(e)}};
  const createRevenue=async()=>{try{await financialErpApi.createRevenue({...revenueForm,company_id:companyId,amount:Number(revenueForm.amount)});setRevenues((await financialErpApi.revenues()).items);toast({title:'تم تسجيل وصل القبض'})}catch(e){notify(e)}};
  const createPricing=async()=>{try{await financialErpApi.createPricingItem(companyId,{...pricingForm,company_unit_price:Number(pricingForm.company_unit_price),mfec_share_value:Number(pricingForm.mfec_share_value),effective_to:null});setPricing((await financialErpApi.pricingItems(companyId)).items);toast({title:'تمت إضافة بند التحاسب'})}catch(e){notify(e)}};
  const go=(key:string)=>nav(`${ROUTES.ADMIN_FINANCIAL}/${key}`);

  return <div className="min-h-screen bg-slate-50" dir="rtl">
    <header className="text-white" style={{background:brand.header_color||brand.primary_color}}>
      <div className="max-w-[1500px] mx-auto p-4 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3"><img src={resolveAssetUrl(brand.system_logo)} className="w-12 h-12 object-contain"/><div><h1 className="text-xl font-bold">الإدارة المالية والنشاطات</h1><p className="text-xs opacity-80">MFEC Financial ERP</p></div></div>
        <Button variant="outline" className="bg-white/10 text-white" onClick={()=>nav(ROUTES.ADMIN)}>إدارة العضويات</Button>
      </div>
    </header>
    <div className="max-w-[1500px] mx-auto p-3 md:p-6 grid lg:grid-cols-[230px_1fr] gap-4">
      <aside className="bg-white border rounded-xl p-2 h-fit lg:sticky lg:top-4">
        {sections.map(([key,label,Icon])=><Button key={key} variant={section===key?'default':'ghost'} className="w-full justify-start mb-1" onClick={()=>go(key)}><Icon className="w-4 h-4 ml-2"/>{label}</Button>)}
        <Button variant="ghost" className="w-full justify-start" onClick={()=>nav(`${ROUTES.ADMIN_FINANCIAL}/legacy`)}>الواجهة السابقة</Button>
      </aside>
      <main className="space-y-4 min-w-0">
        <Card><CardContent className="p-3 flex gap-3 flex-wrap items-end">
          <div><Label>الشركة</Label><select className="h-10 border rounded-md px-3 min-w-52" value={companyId} onChange={e=>setCompanyId(Number(e.target.value))}>{companies.map(c=><option key={c.id} value={c.id}>{c.name} · {c.service_type_name}</option>)}</select></div>
          <div><Label>السنة</Label><Input className="w-28" type="number" value={year} onChange={e=>setYear(Number(e.target.value))}/></div>
          <div><Label>الشهر</Label><Input className="w-24" type="number" min={1} max={12} value={month} onChange={e=>setMonth(Number(e.target.value))}/></div>
        </CardContent></Card>

        {section==='dashboard'&&<><div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-3">
          {[['الإيراد المستحق',dashboard?.accrued_revenue],['المصاريف',dashboard?.expenses],['الربح التقريبي',dashboard?.estimated_profit],['المستحق غير المقبوض',dashboard?.outstanding_receivable]].map(([x,v])=><Card key={x as string}><CardContent className="p-5"><p className="text-sm text-muted-foreground">{x}</p><strong className="text-2xl">{money(v as number)}</strong></CardContent></Card>)}
        </div><Card><CardHeader><CardTitle>الأداء المالي الفعلي</CardTitle></CardHeader><CardContent className="grid md:grid-cols-3 gap-4">{[['الإيراد المقبوض',dashboard?.actual_revenue],['إجمالي المصاريف',dashboard?.expenses],['صافي النتيجة الفعلية',dashboard?.actual_net_result]].map(([x,v])=><div key={x as string} className="border rounded-lg p-4"><p>{x}</p><b className="text-xl">{money(v as number)}</b></div>)}</CardContent></Card></>}

        {section==='companies'&&<><Card><CardHeader><CardTitle>إضافة فقرة تحاسب</CardTitle></CardHeader><CardContent className="grid md:grid-cols-3 gap-3">
          <Input placeholder="اسم الفقرة: كارتون/كيلو" value={pricingForm.name} onChange={e=>setPricingForm({...pricingForm,name:e.target.value})}/><Input placeholder="الوحدة" value={pricingForm.unit} onChange={e=>setPricingForm({...pricingForm,unit:e.target.value})}/>
          <Input type="number" placeholder="سعر الشركة مع العضو" value={pricingForm.company_unit_price} onChange={e=>setPricingForm({...pricingForm,company_unit_price:e.target.value})}/>
          <select className="border rounded-md px-3" value={pricingForm.mfec_share_type} onChange={e=>setPricingForm({...pricingForm,mfec_share_type:e.target.value})}><option value="fixed">مبلغ ثابت</option><option value="percentage">نسبة %</option></select>
          <Input type="number" placeholder="حصة MFEC" value={pricingForm.mfec_share_value} onChange={e=>setPricingForm({...pricingForm,mfec_share_value:e.target.value})}/><Button disabled={!can('financial.pricing.manage')} onClick={createPricing}>+ إضافة فقرة تحاسب</Button>
        </CardContent></Card><DataTable headers={['الفقرة','الوحدة','سعر الشركة','حصة MFEC']} rows={pricing.map(x=>[x.name,x.unit,money(x.current_version?.company_unit_price),`${x.current_version?.mfec_share_value||0}${x.current_version?.mfec_share_type==='percentage'?'%':' د.ع'}`])}/></>}

        {section==='links'&&<Card><CardContent className="p-8 text-center"><Link2 className="w-10 h-10 mx-auto mb-3"/><h2 className="font-bold">ارتباطات الأعضاء والفقرات والملحقات</h2><p className="text-muted-foreground my-3">تُدار بيانات العميل، رابط بوابة الشركة، الأسعار الخاصة والملحق الثلاثي من شاشة الارتباطات الحالية.</p><Button onClick={()=>nav(`${ROUTES.ADMIN_FINANCIAL}/legacy`)}>فتح إدارة الارتباطات</Button></CardContent></Card>}

        {section==='monthly'&&<><Card><CardContent className="p-4 flex gap-2 flex-wrap"><Button onClick={loadGrid}>تحميل جميع الأعضاء وفقراتهم</Button><Badge>{statementStatus==='approved'?'معتمد':'مسودة'}</Badge>{statementId&&statementStatus!=='approved'&&can('financial.monthly.approve')&&<Button variant="outline" onClick={async()=>{await saveGrid();await financialErpApi.approveStatement(statementId);setStatementStatus('approved')}}>اعتماد الكشف كاملًا</Button>}{statementId&&statementStatus==='approved'&&can('financial.monthly.reopen')&&<Button variant="destructive" onClick={async()=>{const reason=prompt('سبب إعادة الفتح');if(reason){await financialErpApi.reopenStatement(statementId,reason);setStatementStatus('draft')}}}>إعادة فتح</Button>}</CardContent></Card>
          <div className="overflow-auto bg-white border rounded-xl"><table className="w-full text-sm"><thead className="bg-slate-100"><tr><th className="p-3 text-right">العضو</th><th>بيانات الشركة</th><th>الفقرة</th><th>الكمية الشهرية</th><th>الحالة</th></tr></thead><tbody>{grid.map((r,i)=><tr key={r.account_item_id} className="border-t"><td className="p-3">{r.membership_number} · {r.member_name}<small className="block">{r.governorate}</small></td><td>{r.registered_name||'-'}<small className="block">{r.customer_code}</small>{r.customer_portal_url&&<a className="text-blue-600 block" href={r.customer_portal_url} target="_blank" rel="noreferrer">فتح رابط العميل</a>}</td><td>{r.pricing_item_name} ({r.unit})</td><td><Input disabled={statementStatus==='approved'} className="w-32" type="number" min={0} value={r.quantity} onChange={e=>setGrid(g=>g.map((x,n)=>n===i?{...x,quantity:Number(e.target.value)}:x))}/></td><td><Badge variant={r.settlement_status==='settled'?'default':'outline'}>{r.settlement_status==='settled'?'تم التحاسب':'غير محاسب'}</Badge></td></tr>)}</tbody></table></div>
          {!!grid.length&&statementStatus!=='approved'&&<Button disabled={busy} onClick={saveGrid}>حفظ جماعي</Button>}</>}

        {section==='reports'&&<><div className="flex gap-2 flex-wrap"><Button onClick={loadReport}>طلب كشف</Button><Button variant="outline" onClick={()=>financialErpApi.exportReport(reportQuery)}>تصدير Excel</Button><Button variant="outline" onClick={()=>window.print()}>طباعة / PDF</Button></div>
          <div className="grid sm:grid-cols-3 gap-2">{[['حجم الأعمال',totals.gross_business_amount],['حصة MFEC',totals.mfec_due_amount],['المقبوض',totals.received_amount],['المتبقي',totals.outstanding_receivable]].map(([x,v])=><Card key={x as string}><CardContent className="p-3"><small>{x}</small><b className="block">{money(v as number)}</b></CardContent></Card>)}</div>
          <div className="overflow-auto bg-white border rounded-xl print:border-0"><table className="w-full text-xs"><thead><tr className="bg-slate-100"><th className="p-3 print:hidden"><input type="checkbox" onChange={e=>setSelected(e.target.checked?report.map(x=>x.id):[])}/></th><th>العضو</th><th>الشركة</th><th>الفقرة</th><th>الكمية</th><th>حجم الأعمال</th><th>حصة MFEC</th><th>التحاسب</th><th>المقبوض</th><th>المتبقي</th></tr></thead><tbody>{report.map(r=><tr key={r.id} className="border-t text-center"><td className="p-3 print:hidden"><input type="checkbox" checked={selected.includes(r.id)} onChange={e=>setSelected(s=>e.target.checked?[...s,r.id]:s.filter(x=>x!==r.id))}/></td><td>{r.member_name}<small className="block">{r.governorate}</small></td><td>{r.company_name}</td><td>{r.pricing_item}</td><td>{r.quantity} {r.unit}</td><td>{money(r.gross_business_amount)}</td><td>{money(r.mfec_due_amount)}</td><td>{r.settlement_status==='settled'?'تم التحاسب':'غير محاسب'}</td><td>{money(r.received_amount)}</td><td>{money(r.outstanding_receivable)}</td></tr>)}</tbody></table></div></>}

        {section==='revenues'&&<><Card><CardHeader><CardTitle>تسجيل إيراد فعلي</CardTitle></CardHeader><CardContent className="grid md:grid-cols-3 gap-3"><Input placeholder="رقم وصل القبض" value={revenueForm.receipt_number} onChange={e=>setRevenueForm({...revenueForm,receipt_number:e.target.value})}/><Input type="date" value={revenueForm.received_at} onChange={e=>setRevenueForm({...revenueForm,received_at:e.target.value})}/><Input type="number" placeholder="المبلغ" value={revenueForm.amount} onChange={e=>setRevenueForm({...revenueForm,amount:e.target.value})}/><Input placeholder="طريقة الاستلام" value={revenueForm.receipt_method} onChange={e=>setRevenueForm({...revenueForm,receipt_method:e.target.value})}/><Input placeholder="وصف الإيراد" value={revenueForm.description} onChange={e=>setRevenueForm({...revenueForm,description:e.target.value})}/><Button disabled={!can('financial.revenues.create')} onClick={createRevenue}>حفظ الوصل</Button></CardContent></Card><DataTable headers={['الوصل','التاريخ','المبلغ','المخصص','المتبقي']} rows={revenues.map(x=>[x.receipt_number,x.received_at,money(x.amount),money(x.allocated),money(x.remaining)])}/></>}
        {section==='settlements'&&<><Card><CardContent className="p-5"><h2 className="font-bold">دفعات التسوية</h2><p className="text-muted-foreground">حدد الأسطر من التقرير ثم أنشئ دفعة تسوية موحدة. العكس محفوظ ولا يحذف السجل.</p></CardContent></Card><DataTable headers={['رقم الدفعة','التاريخ','المرجع','الحالة']} rows={settlements.map(x=>[x.batch_number,x.settled_at,x.reference_number||'-',x.status==='reversed'?'معكوسة':'فعالة'])}/></>}
      </main>
    </div>
  </div>
}

function DataTable({headers,rows}:{headers:string[];rows:(string|number)[][]}){
  return <div className="overflow-auto bg-white border rounded-xl"><table className="w-full text-sm"><thead><tr className="bg-slate-100">{headers.map(x=><th key={x} className="p-3 text-right">{x}</th>)}</tr></thead><tbody>{rows.map((r,i)=><tr key={i} className="border-t">{r.map((x,j)=><td key={j} className="p-3">{x}</td>)}</tr>)}</tbody></table></div>
}
