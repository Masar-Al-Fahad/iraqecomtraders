import { useEffect, useMemo, useRef, useState } from 'react';
import { Eye, FileSpreadsheet, Printer, RotateCcw, Save, Scale, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { financialErpApi } from '@/lib/financialErpApi';
import type { Attachment, Company, MemberOption, PricingItem, ReportLine, ServiceType, Settlement, StatementGridRow } from '@/types/financialErp';
import { CompactTable, Empty, FileButton, FormDialog, PageTitle, SafeDateInput, StatusBadge, money } from './FinancialUi';

type Props={companies:Company[];services:ServiceType[];can:(key:string)=>boolean;finance:boolean;notify:(e:unknown)=>void;success:(message:string)=>void};
const now=new Date();const today=()=>new Date().toISOString().slice(0,10);
const monthRange=(year:number,month:number)=>({from:`${year}-${String(month).padStart(2,'0')}-01`,to:new Date(year,month,0).toISOString().slice(0,10)});

function calcLineAmounts(quantity:number, unitPrice:number, shareType?:'fixed'|'percentage', shareValue=0){
  const gross=quantity*unitPrice;
  const due=shareType==='percentage'?gross*(shareValue/100):quantity*shareValue;
  return {gross_business_amount:gross, mfec_due_amount:due};
}

function periodFromDate(from:string){
  if(!from || from.length<7)return {year:now.getFullYear(), month:now.getMonth()+1};
  const year=Number(from.slice(0,4));
  const month=Number(from.slice(5,7));
  if(!year||month<1||month>12)return {year:now.getFullYear(), month:now.getMonth()+1};
  return {year, month};
}

export function MonthlyPage({companies,can,notify,success}:Props){
  const [companyId,setCompanyId]=useState<number>(companies[0]?.id||0);
  const initialRange=monthRange(now.getFullYear(), now.getMonth()+1);
  const [dateFrom,setDateFrom]=useState(initialRange.from);
  const [dateTo,setDateTo]=useState(initialRange.to);
  const [grid,setGrid]=useState<StatementGridRow[]>([]);
  const [statementId,setStatementId]=useState<number|null>(null);
  const [status,setStatus]=useState('draft');
  const [memberFilter,setMemberFilter]=useState('');
  const [itemFilter,setItemFilter]=useState('');
  const [governorate,setGovernorate]=useState('');
  const [receivedAt,setReceivedAt]=useState('');
  const [notes,setNotes]=useState('');
  const [attachments,setAttachments]=useState<Attachment[]>([]);
  const [busy,setBusy]=useState(false);
  const inputs=useRef<(HTMLInputElement|null)[]>([]);

  const {year, month}=useMemo(()=>periodFromDate(dateFrom),[dateFrom]);

  useEffect(()=>{if(!companyId&&companies[0])setCompanyId(companies[0].id)},[companies,companyId]);

  // Client-side only — never send "all" filter labels as API integers.
  const visible=useMemo(()=>grid.filter(row=>
    (!memberFilter||String(row.member_id)===memberFilter)&&
    (!itemFilter||String(row.pricing_item_id)===itemFilter)&&
    (!governorate.trim()||row.governorate.includes(governorate.trim()))
  ),[grid,memberFilter,itemFilter,governorate]);

  const memberOptions=useMemo(()=>Array.from(new Map(grid.map(r=>[r.member_id,r])).values()),[grid]);
  const itemOptions=useMemo(()=>Array.from(new Map(grid.map(r=>[r.pricing_item_id,r])).values()),[grid]);

  const applyLoaded=async(x:Awaited<ReturnType<typeof financialErpApi.statementGrid>>)=>{
    setGrid(x.items);
    setStatementId(x.statement_id);
    setStatus(x.status);
    setDateFrom(x.period_start);
    setDateTo(x.period_end);
    setReceivedAt(x.received_at||'');
    setNotes(x.notes||'');
    setAttachments(x.statement_id?(await financialErpApi.statementAttachments(x.statement_id)).items:[]);
  };

  const load=async()=>{
    if(!(companyId>0)){notify(new Error('اختر شركة صحيحة قبل التحميل'));return}
    setBusy(true);
    try{
      await applyLoaded(await financialErpApi.statementGrid(companyId, year, month));
    }catch(e){notify(e)}
    finally{setBusy(false)}
  };

  const setQuantity=(accountItemId:number, raw:string)=>{
    if(raw.trim()===''){
      setGrid(rows=>rows.map(x=>x.account_item_id===accountItemId?{
        ...x, quantity:0, gross_business_amount:0, mfec_due_amount:0,
      }:x));
      return;
    }
    const quantity=Number(raw);
    if(Number.isNaN(quantity)||quantity<0)return;
    setGrid(rows=>rows.map(x=>{
      if(x.account_item_id!==accountItemId)return x;
      return {
        ...x,
        quantity,
        ...calcLineAmounts(quantity, Number(x.effective_unit_price||0), x.effective_mfec_share_type, Number(x.effective_mfec_share_value||0)),
      };
    }));
  };

  const focusNextQuantity=(index:number)=>{
    const next=inputs.current[index+1];
    if(!next)return;
    next.focus();
    next.select();
  };

  const save=async(approveAfter=false)=>{
    if(!grid.length){notify(new Error('حمّل قائمة الأعضاء والفقرات قبل الحفظ'));return}
    if(dateFrom&&dateTo&&dateTo<dateFrom){notify(new Error('تاريخ نهاية الفترة يجب أن يكون بعد تاريخ البداية'));return}
    if(!(companyId>0)){notify(new Error('شركة غير صالحة'));return}
    setBusy(true);
    try{
      const x=await financialErpApi.saveStatement({
        company_id:companyId,
        accounting_year:year,
        accounting_month:month,
        period_start:dateFrom||null,
        period_end:dateTo||null,
        received_at:receivedAt||null,
        notes:notes||null,
        lines:grid.map(r=>({account_item_id:r.account_item_id, quantity:r.quantity||0, excluded:!!r.excluded})),
      });
      setStatementId(x.statement_id);
      setStatus(x.status);
      let message=`تم حفظ ${x.saved} صفًا`;
      if(x.failed)message+=`، وفشل ${x.failed}`;
      if(approveAfter&&can('financial.monthly.approve')){
        await financialErpApi.approveStatement(x.statement_id);
        setStatus('approved');
        message+=' وتم اعتماد الإدخال';
      }
      success(message);
      await applyLoaded(await financialErpApi.statementGrid(companyId, year, month));
      return x.statement_id;
    }catch(e){notify(e)}
    finally{setBusy(false)}
  };

  const upload=async(file:File, replacedId?:number)=>{
    const id=statementId||await save(false);
    if(!id)return;
    try{
      const up=await financialErpApi.upload('statements',file);
      await financialErpApi.addStatementAttachment(id,{
        ...up,
        original_filename:file.name,
        mime_type:file.type,
        size_bytes:file.size,
        replaced_id:replacedId||null,
      });
      setAttachments((await financialErpApi.statementAttachments(id)).items);
      success(replacedId?'تم استبدال الكشف الأصلي':'تم رفع الكشف الأصلي');
    }catch(e){notify(e)}
  };

  const canEnter=status!=='approved'&&can('financial.monthly.enter');
  const companyName=companies.find(c=>c.id===companyId)?.name||'';

  return <div className="space-y-4">
    <PageTitle title="الإدخال الشهري" description="كشف جماعي لشركة واحدة: حمّل كل الارتباطات، اكتب الكمية فقط لكل فقرة، ثم احفظ واعتمد. الأسعار وحصص MFEC تُجلب تلقائيًا من تسعير الشركة أو Override العضو."/>
    <Card><CardContent className="p-3 grid sm:grid-cols-2 xl:grid-cols-4 gap-3 items-end">
      <Field label="الشركة"><select className="h-10 border rounded-md px-3 min-w-56" value={companyId||''} onChange={e=>{
        const id=Number(e.target.value);
        setCompanyId(Number.isFinite(id)&&id>0?id:0);
        setGrid([]);
        setStatementId(null);
        setMemberFilter('');
        setItemFilter('');
      }}>{companies.map(c=><option key={c.id} value={c.id}>{c.name} · {c.service_type_name}</option>)}</select></Field>
      <Field label="من تاريخ"><SafeDateInput value={dateFrom} onChange={e=>{
        const next=e.target.value;
        setDateFrom(next);
        const p=periodFromDate(next);
        const range=monthRange(p.year,p.month);
        setDateTo(range.to);
        setGrid([]);
        setStatementId(null);
      }}/></Field>
      <Field label="إلى تاريخ"><SafeDateInput value={dateTo} onChange={e=>setDateTo(e.target.value)}/></Field>
      <Field label="العضو"><select className="h-10 border rounded-md px-2 w-full" value={memberFilter} onChange={e=>setMemberFilter(e.target.value)}><option value="">كل الأعضاء</option>{memberOptions.map(r=><option key={r.member_id} value={r.member_id}>{r.membership_number} · {r.member_name}</option>)}</select></Field>
      <Field label="الفقرة"><select className="h-10 border rounded-md px-2 w-full" value={itemFilter} onChange={e=>setItemFilter(e.target.value)}><option value="">كل الفقرات</option>{itemOptions.map(r=><option key={r.pricing_item_id} value={r.pricing_item_id}>{r.pricing_item_name}</option>)}</select></Field>
      <Field label="المحافظة"><Input value={governorate} onChange={e=>setGovernorate(e.target.value)} placeholder="كل المحافظات"/></Field>
      <Field label="تاريخ استلام الكشف"><SafeDateInput value={receivedAt} onChange={e=>setReceivedAt(e.target.value)}/></Field>
      <Field label="ملاحظات الكشف"><Input value={notes} onChange={e=>setNotes(e.target.value)}/></Field>
      <Button onClick={()=>void load()} disabled={busy||!(companyId>0)}>تحميل جميع الارتباطات</Button>
      <StatusBadge value={status}/>
      {canEnter&&<FileButton label="رفع الكشف الأصلي" accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png,.webp,application/pdf,image/*" onFile={upload}/>}
      {statementId&&attachments.map(a=><div key={a.id} className="flex gap-1 flex-wrap items-center">
        <Button type="button" size="sm" variant="outline" onClick={()=>financialErpApi.openDocument(a.object_key)}><Eye className="w-4 h-4 ml-1"/>{a.original_filename}</Button>
        {status!=='approved'&&can('financial.monthly.edit')&&<>
          <FileButton label="استبدال" onFile={file=>upload(file,a.id)}/>
          <Button type="button" size="icon" variant="ghost" onClick={async()=>{await financialErpApi.deleteStatementAttachment(statementId,a.id);setAttachments((await financialErpApi.statementAttachments(statementId)).items)}}><Trash2 className="w-4 h-4 text-red-600"/></Button>
        </>}
      </div>)}
    </CardContent></Card>

    <div className="overflow-auto max-h-[62vh] border rounded-xl bg-white">
      <table className="w-full text-sm whitespace-nowrap">
        <thead className="bg-slate-100 sticky top-0 z-20">
          <tr>
            <th className="p-3 text-right sticky right-0 bg-slate-100 z-30 min-w-[170px]">العضو</th>
            <th className="p-3 text-right">الشركة/العميل</th>
            <th className="p-3 text-right">الفقرة</th>
            <th className="p-3 text-right">الوحدة</th>
            <th className="p-3 text-right">الكمية</th>
            <th className="p-3 text-right">سعر العميل</th>
            <th className="p-3 text-right">حجم الأعمال</th>
            <th className="p-3 text-right">حصة MFEC</th>
            <th className="p-3 text-right">التحاسب</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((r,i)=>{
            const prev=visible[i-1];
            const memberStart=!prev||prev.member_id!==r.member_id;
            return (
              <tr key={r.account_item_id} className={`border-t hover:bg-blue-50/40 ${memberStart?'border-t-2 border-t-slate-300':''}`}>
                <td className="p-3 sticky right-0 bg-white min-w-[170px]">
                  {memberStart?(
                    <>
                      <b>{r.member_name}</b>
                      <small className="block text-slate-500">{r.membership_number}{r.governorate?` · ${r.governorate}`:''}</small>
                    </>
                  ):<span className="text-slate-300">↳</span>}
                </td>
                <td className="p-3">
                  {r.registered_name||companyName||'-'}
                  <small className="block text-slate-500">{r.customer_code||r.registered_phone||r.company_name||''}</small>
                </td>
                <td className="p-3">{r.pricing_item_name}</td>
                <td className="p-3">{r.unit}</td>
                <td className="p-2">
                  <Input
                    ref={el=>{inputs.current[i]=el}}
                    disabled={!canEnter}
                    className="w-28 text-center font-bold"
                    type="number"
                    min={0}
                    step="any"
                    placeholder="—"
                    value={r.quantity?r.quantity:''}
                    onChange={e=>setQuantity(r.account_item_id, e.target.value)}
                    onFocus={e=>e.currentTarget.select()}
                    onKeyDown={e=>{
                      if(e.key==='Enter'){
                        e.preventDefault();
                        focusNextQuantity(i);
                      }
                    }}
                  />
                </td>
                <td className="p-3 text-slate-700">{money(r.effective_unit_price)}</td>
                <td className="p-3 font-semibold">{money(r.gross_business_amount)}</td>
                <td className="p-3 font-semibold text-emerald-800">{money(r.mfec_due_amount)}</td>
                <td className="p-3"><StatusBadge value={r.settlement_status||'unsettled'}/></td>
              </tr>
            );
          })}
          {!grid.length&&(
            <tr><td colSpan={9}><Empty title="لم يتم تحميل الجدول" description="اختر الشركة والفترة ثم اضغط تحميل جميع الارتباطات."/></td></tr>
          )}
          {!!grid.length&&!visible.length&&(
            <tr><td colSpan={9}><Empty title="لا توجد صفوف مطابقة" description="عدّل فلاتر العضو أو الفقرة أو المحافظة (فلترة محلية فقط)."/></td></tr>
          )}
        </tbody>
      </table>
    </div>

    {!!grid.length&&(
      <div className="flex flex-wrap gap-2 items-center">
        <span className="text-sm text-slate-600">المعروض {visible.length} من {grid.length} فقرة · الفترة {year}/{String(month).padStart(2,'0')}</span>
        {canEnter&&can('financial.monthly.approve')&&(
          <Button disabled={busy} onClick={()=>void save(true)}><Save className="w-4 h-4 ml-2"/>حفظ واعتماد الإدخال</Button>
        )}
        {canEnter&&!can('financial.monthly.approve')&&(
          <Button disabled={busy} onClick={()=>void save(false)}><Save className="w-4 h-4 ml-2"/>حفظ الإدخال</Button>
        )}
        {canEnter&&can('financial.monthly.approve')&&(
          <Button variant="outline" disabled={busy} onClick={()=>void save(false)}>حفظ مسودة فقط</Button>
        )}
        {status==='approved'&&can('financial.monthly.reopen')&&(
          <Button variant="destructive" onClick={async()=>{
            const reason=prompt('سبب إعادة فتح الكشف (يسجل بالتدقيق)');
            if(reason&&statementId){
              try{await financialErpApi.reopenStatement(statementId,reason);setStatus('draft')}
              catch(e){notify(e)}
            }
          }}><RotateCcw className="w-4 h-4 ml-2"/>إعادة فتح</Button>
        )}
      </div>
    )}
  </div>;
}

type ReportFilters={accounting_year:string;accounting_month:string;date_from:string;date_to:string;company_id:string;member_id:string;governorate:string;service_type_id:string;pricing_item_id:string;settlement_status:string};
const initialFilters:ReportFilters={accounting_year:String(now.getFullYear()),accounting_month:String(now.getMonth()+1),date_from:'',date_to:'',company_id:'',member_id:'',governorate:'',service_type_id:'',pricing_item_id:'',settlement_status:''};
export function ReportsPage({companies,services,can,notify}:Props){
  const [filters,setFilters]=useState(initialFilters);const [members,setMembers]=useState<MemberOption[]>([]);const [pricing,setPricing]=useState<PricingItem[]>([]);
  const [rows,setRows]=useState<ReportLine[]>([]);const [totals,setTotals]=useState<Record<string,number>>({});const [selected,setSelected]=useState<number[]>([]);
  useEffect(()=>{financialErpApi.members().then(x=>setMembers(x.items)).catch(()=>{})},[]);
  useEffect(()=>{if(filters.company_id)financialErpApi.pricingItems(Number(filters.company_id)).then(x=>setPricing(x.items));else setPricing([])},[filters.company_id]);
  const query=useMemo(()=>financialErpApi.query({...filters,selected_ids:selected.length?selected:undefined}),[filters,selected]);
  const load=async()=>{try{const x=await financialErpApi.report(financialErpApi.query(filters));setRows(x.items);setTotals(x.totals);setSelected([])}catch(e){notify(e)}};
  const exportXlsx=()=>financialErpApi.exportReport(query).catch(notify);
  return <div className="space-y-4 print:bg-white">
    <PageTitle title="التقارير المالية" description="كشف الشركات أو عضو واحد عبر جميع الشركات، مع إجماليات التحاسب والقبض."
      actions={<>{can('financial.reports.xlsx')&&<Button variant="outline" onClick={exportXlsx}><FileSpreadsheet className="w-4 h-4 ml-2"/>Excel حقيقي</Button>}{can('financial.reports.print')&&<Button variant="outline" onClick={()=>window.print()}><Printer className="w-4 h-4 ml-2"/>طباعة</Button>}{can('financial.reports.pdf')&&<Button variant="outline" onClick={()=>window.print()}>PDF</Button>}</>}/>
    <Card className="print:hidden"><CardContent className="p-3 grid sm:grid-cols-2 lg:grid-cols-5 gap-2">
      <Select value={filters.company_id} onChange={v=>setFilters({...filters,company_id:v})} first="كل الشركات" items={companies.map(x=>[x.id,x.name])}/>
      <Select value={filters.member_id} onChange={v=>setFilters({...filters,member_id:v})} first="كل الأعضاء" items={members.map(x=>[x.id,`${x.membership_number} · ${x.member_name}`])}/>
      <Select value={filters.service_type_id} onChange={v=>setFilters({...filters,service_type_id:v})} first="كل الخدمات" items={services.map(x=>[x.id,x.name])}/>
      <Select value={filters.pricing_item_id} onChange={v=>setFilters({...filters,pricing_item_id:v})} first="كل الفقرات" items={pricing.map(x=>[x.id,x.name])}/>
      <select className="h-10 border rounded-md px-2" value={filters.settlement_status} onChange={e=>setFilters({...filters,settlement_status:e.target.value})}><option value="">كل حالات التحاسب</option><option value="settled">تم التحاسب</option><option value="unsettled">غير محاسب</option></select>
      <Input placeholder="المحافظة" value={filters.governorate} onChange={e=>setFilters({...filters,governorate:e.target.value})}/><Input type="number" placeholder="السنة" value={filters.accounting_year} onChange={e=>setFilters({...filters,accounting_year:e.target.value})}/><Input type="number" min={1} max={12} placeholder="الشهر" value={filters.accounting_month} onChange={e=>setFilters({...filters,accounting_month:e.target.value})}/><SafeDateInput value={filters.date_from} onChange={e=>setFilters({...filters,date_from:e.target.value,accounting_year:'',accounting_month:''})}/><SafeDateInput value={filters.date_to} onChange={e=>setFilters({...filters,date_to:e.target.value,accounting_year:'',accounting_month:''})}/><Button type="button" onClick={load}>عرض الكشف</Button>
    </CardContent></Card>
    <div className="grid grid-cols-2 lg:grid-cols-6 gap-2">{[['حجم الأعمال','gross_business_amount'],['استحقاق MFEC','mfec_due_amount'],['تم التحاسب','settled_amount'],['غير محاسب','unsettled_amount'],['المقبوض','received_amount'],['المتبقي','outstanding_receivable']].map(([label,key])=><Card key={key}><CardContent className="p-3"><small className="text-slate-500">{label}</small><b className="block">{money(totals[key])}</b></CardContent></Card>)}</div>
    <CompactTable headers={['اختيار','العضو','الشركة / الخدمة','الفقرة','الكمية','حجم الأعمال','استحقاق MFEC','التحاسب','المقبوض','المتبقي']}>
      {rows.map(r=><tr key={r.id} className={`border-t text-center ${selected.length&&!selected.includes(r.id)?'print:hidden':''}`}><td className="p-3 print:hidden"><Checkbox checked={selected.includes(r.id)} onCheckedChange={v=>setSelected(s=>v?[...s,r.id]:s.filter(x=>x!==r.id))}/></td><td className="text-right">{r.member_name}<small className="block">{r.membership_number} · {r.governorate}</small></td><td>{r.company_name}<small className="block">{r.service_type}</small></td><td>{r.pricing_item}</td><td>{r.quantity} {r.unit}</td><td>{money(r.gross_business_amount)}</td><td>{money(r.mfec_due_amount)}</td><td><StatusBadge value={r.settlement_status}/></td><td>{money(r.received_amount)}</td><td>{money(r.outstanding_receivable)}</td></tr>)}
      {!!rows.length&&<tr className="bg-slate-50 print:hidden"><td className="p-3"><Checkbox checked={selected.length===rows.length} onCheckedChange={v=>setSelected(v?rows.map(x=>x.id):[])}/></td><td colSpan={9}>تحديد الكل — التصدير يقتصر على الصفوف المحددة، أو كل الفلتر عند عدم التحديد.</td></tr>}
    </CompactTable>
  </div>;
}

export function SettlementsPage({companies,can,notify}:Props){
  const [companyId,setCompanyId]=useState<number>(companies[0]?.id||0);const [year,setYear]=useState(now.getFullYear());const [month,setMonth]=useState(now.getMonth()+1);
  const [lines,setLines]=useState<ReportLine[]>([]);const [selected,setSelected]=useState<number[]>([]);const [batches,setBatches]=useState<Settlement[]>([]);
  const [lineFilter,setLineFilter]=useState('unsettled');const [filter,setFilter]=useState('all');const [open,setOpen]=useState(false);const [details,setDetails]=useState<any[]>([]);
  const [form,setForm]=useState({settled_at:today(),reference_number:'',notes:'',attachment_key:''});
  useEffect(()=>{if(!companyId&&companies[0])setCompanyId(companies[0].id)},[companies]);
  const load=async()=>{if(!companyId)return;try{const [r,b]=await Promise.all([financialErpApi.report(financialErpApi.query({company_id:companyId,accounting_year:year,accounting_month:month,settlement_status:lineFilter==='all'?'':lineFilter})),financialErpApi.settlements(companyId)]);setLines(r.items);setBatches(b.items);setSelected([])}catch(e){notify(e)}};
  const create=async()=>{try{await financialErpApi.createSettlement({company_id:companyId,entry_line_ids:selected,...form});setOpen(false);await load()}catch(e){notify(e)}};
  return <div className="space-y-4"><PageTitle title="التسويات" description="تحاسب جماعي لأسطر كشوف معتمدة، مع دفعة مرقمة وعكس مدقق لا يحذف الأسطر."/>
    <Card><CardContent className="p-3 flex gap-2 items-end flex-wrap"><Field label="الشركة"><select className="h-10 border rounded-md px-3 min-w-56" value={companyId} onChange={e=>setCompanyId(Number(e.target.value))}>{companies.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></Field><Field label="السنة"><Input className="w-28" type="number" value={year} onChange={e=>setYear(Number(e.target.value))}/></Field><Field label="الشهر"><Input className="w-24" type="number" value={month} onChange={e=>setMonth(Number(e.target.value))}/></Field><Field label="حالة السطر"><select className="h-10 border rounded-md px-3" value={lineFilter} onChange={e=>setLineFilter(e.target.value)}><option value="all">الكل</option><option value="settled">تم التحاسب</option><option value="unsettled">غير محاسب</option></select></Field><Button onClick={load}>تحميل</Button>{can('financial.settlements.create')&&<Button disabled={!selected.length||selected.some(id=>lines.find(x=>x.id===id)?.settlement_status==='settled')} onClick={()=>setOpen(true)}><Scale className="w-4 h-4 ml-2"/>تم التحاسب ({selected.length})</Button>}</CardContent></Card>
    <CompactTable headers={['','العضو','الفقرة','الكمية','حصة MFEC','الحالة']}>{lines.map(r=><tr key={r.id} className="border-t"><td className="p-3"><Checkbox checked={selected.includes(r.id)} onCheckedChange={v=>setSelected(s=>v?[...s,r.id]:s.filter(x=>x!==r.id))}/></td><td>{r.member_name}<small className="block">{r.membership_number}</small></td><td>{r.pricing_item}</td><td>{r.quantity} {r.unit}</td><td>{money(r.mfec_due_amount)}</td><td><StatusBadge value={r.settlement_status}/></td></tr>)}</CompactTable>
    <div className="flex gap-2"><h3 className="font-bold self-center">دفعات التسوية</h3><select className="h-9 border rounded px-2" value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">الكل</option><option value="active">فعالة</option><option value="reversed">معكوسة</option></select></div>
    <CompactTable headers={['رقم الدفعة','التاريخ','المرجع','الأسطر','الحالة','الإجراءات']}>{batches.filter(x=>filter==='all'||x.status===filter).map(b=><tr key={b.id} className="border-t"><td className="p-3 font-mono">{b.batch_number}</td><td>{b.settled_at}</td><td>{b.reference_number||'-'}</td><td>{b.line_count}</td><td><StatusBadge value={b.status}/></td><td><Button size="sm" variant="outline" onClick={async()=>{setDetails((await financialErpApi.settlementLines(b.id)).items)}}><Eye className="w-4 h-4 ml-1"/>الأسطر</Button>{b.status==='active'&&can('financial.settlements.reverse')&&<Button size="sm" variant="ghost" onClick={async()=>{const reason=prompt('سبب عكس التسوية');if(reason){await financialErpApi.reverseSettlement(b.id,reason);await load()}}}><RotateCcw className="w-4 h-4 text-red-600"/></Button>}</td></tr>)}</CompactTable>
    {!!details.length&&<Card><CardContent className="p-4"><h3 className="font-bold mb-2">أسطر الدفعة</h3>{details.map(x=><div key={x.id} className="flex justify-between py-2 border-t"><span>{x.membership_number} · {x.member_name} · {x.pricing_item}</span><b>{money(x.amount)}</b></div>)}</CardContent></Card>}
    <FormDialog open={open} onOpenChange={setOpen} title="تأكيد تم التحاسب"><div className="grid md:grid-cols-2 gap-3"><Field label="تاريخ التحاسب"><SafeDateInput value={form.settled_at} onChange={e=>setForm({...form,settled_at:e.target.value})}/></Field><Field label="المرجع"><Input value={form.reference_number} onChange={e=>setForm({...form,reference_number:e.target.value})}/></Field><Field label="ملاحظات"><Textarea value={form.notes} onChange={e=>setForm({...form,notes:e.target.value})}/></Field><Field label="مرفق اختياري"><FileButton label={form.attachment_key?'تم رفع المرفق':'رفع مرفق'} onFile={async file=>{const x=await financialErpApi.upload('settlements',file);setForm({...form,attachment_key:x.object_key})}}/></Field></div><Button type="button" onClick={create}>إنشاء دفعة التسوية</Button></FormDialog>
  </div>;
}

function Field({label,children}:{label:string;children:React.ReactNode}){return <div><Label className="block mb-1">{label}</Label>{children}</div>}
function Select({value,onChange,first,items}:{value:string;onChange:(v:string)=>void;first:string;items:(string|number)[][]}){return <select className="h-10 border rounded-md px-2 bg-white" value={value} onChange={e=>onChange(e.target.value)}><option value="">{first}</option>{items.map(x=><option key={x[0]} value={x[0]}>{x[1]}</option>)}</select>}
