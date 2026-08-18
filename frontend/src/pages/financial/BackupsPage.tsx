import { useEffect, useState } from 'react';
import { Archive, Download, Plus, RotateCcw, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { financialErpApi } from '@/lib/financialErpApi';
import type { FinancialBackup } from '@/types/financialErp';
import { CompactTable, Empty, FormDialog, PageTitle, StatusBadge } from './FinancialUi';

type Props={can:(key:string)=>boolean;notify:(e:unknown)=>void;success:(message:string)=>void};
const size=(bytes:number)=>bytes<1024?`${bytes} B`:bytes<1024*1024?`${(bytes/1024).toFixed(1)} KB`:`${(bytes/1024/1024).toFixed(1)} MB`;

export function BackupsPage({can,notify,success}:Props){
  const [rows,setRows]=useState<FinancialBackup[]>([]);
  const [notes,setNotes]=useState('');const [busy,setBusy]=useState(false);
  const [restore,setRestore]=useState<FinancialBackup>();const [confirmation,setConfirmation]=useState('');const [restoreNotes,setRestoreNotes]=useState('');
  const load=async()=>{try{setRows((await financialErpApi.backups()).items)}catch(e){notify(e)}};
  useEffect(()=>{void load()},[]);
  const create=async()=>{setBusy(true);try{await financialErpApi.createBackup(notes);setNotes('');await load();success('تم إنشاء النسخة الاحتياطية وحفظها في التخزين الخاص')}catch(e){notify(e)}finally{setBusy(false)}};
  const requestRestore=async()=>{if(!restore)return;if(!restoreNotes.trim()){notify(new Error('سبب الاستعادة مطلوب'));return}try{await financialErpApi.requestRestore(restore.id,confirmation,restoreNotes);setRestore(undefined);setConfirmation('');setRestoreNotes('');await load();success('تم تسجيل طلب الاستعادة فقط — لم تُستبدل قاعدة البيانات. راجع الحالة «طلب استعادة» في الجدول.')}catch(e){notify(e)}};
  return <div className="space-y-4">
    <PageTitle title="النسخ الاحتياطية" description="إنشاء النسخ يعمل داخل التطبيق. الاستعادة ليست تنفيذًا تلقائيًا لقاعدة البيانات — الزر يسجّل طلبًا تشغيليًا فقط."/>
    <Card><CardContent className="p-4 grid md:grid-cols-[1fr_auto] gap-3 items-end">
      <div><Label>ملاحظات النسخة</Label><Input value={notes} onChange={e=>setNotes(e.target.value)} placeholder="سبب إنشاء النسخة أو وصفها"/></div>
      {can('backups.create')&&<Button type="button" disabled={busy} onClick={create}><Plus className="w-4 h-4 ml-2"/>{busy?'جاري الإنشاء...':'إنشاء نسخة احتياطية الآن'}</Button>}
    </CardContent></Card>
    <CompactTable headers={['النسخة','النوع','التاريخ والمنشئ','الحجم','الحالة','الملاحظات','الإجراءات']}>
      {rows.map(row=><tr key={row.id} className="border-t">
        <td className="p-3 font-mono">{row.backup_number}<small className="block text-slate-400">{row.checksum_sha256.slice(0,12)}…</small></td>
        <td>{row.kind==='pre_restore'?'قبل الاستعادة':'يدوية'}</td>
        <td>{new Date(row.created_at).toLocaleString('ar-IQ')}<small className="block">{row.created_by}</small></td>
        <td>{size(row.size_bytes)}</td><td><StatusBadge value={row.status}/></td><td>{row.notes||'-'}</td>
        <td className="flex gap-1 py-2">
          {can('backups.download')&&<Button type="button" size="icon" variant="ghost" onClick={()=>financialErpApi.downloadBackup(row.id,row.backup_number).catch(notify)}><Download className="w-4 h-4"/></Button>}
          {can('backups.restore')&&row.status==='ready'&&<Button type="button" size="sm" variant="outline" onClick={()=>setRestore(row)}><RotateCcw className="w-4 h-4 ml-1"/>طلب استعادة</Button>}
          {can('backups.delete')&&<Button type="button" size="icon" variant="ghost" onClick={async()=>{if(!confirm(`حذف النسخة ${row.backup_number}؟`))return;try{await financialErpApi.deleteBackup(row.id);await load();success('تم حذف ملف النسخة مع الاحتفاظ بسجل التدقيق')}catch(e){notify(e)}}}><Trash2 className="w-4 h-4 text-red-600"/></Button>}
        </td>
      </tr>)}
      {!rows.length&&<tr><td colSpan={7}><Empty title="لا توجد نسخ احتياطية" description="أنشئ أول نسخة من الزر أعلاه."/></td></tr>}
    </CompactTable>
    <Card><CardContent className="p-4 space-y-2 text-sm text-amber-900 bg-amber-50">
      <div className="flex gap-3"><Archive className="w-5 h-5 shrink-0"/><div>
        <p className="font-bold">ما الذي يفعله زر «طلب استعادة»؟</p>
        <ul className="list-disc pr-5 mt-1 space-y-1">
          <li>يتحقق من تأكيد <b dir="ltr">RESTORE</b> وسبب الاستعادة.</li>
          <li>ينشئ نسخة تلقائية <b>قبل الطلب</b> (pre_restore) للحالة الحالية.</li>
          <li>يسجّل الطلب في Audit Log ويغيّر حالة النسخة إلى «طلب استعادة».</li>
          <li><b>لا يستبدل قاعدة البيانات ولا يشغّل pg_restore داخل التطبيق</b> — التنفيذ الحقيقي يحتاج إجراءً تشغيليًا خارج التطبيق (Railway/Supabase) باستخدام ملف النسخة المنزَّل.</li>
        </ul>
      </div></div>
    </CardContent></Card>
    <FormDialog open={!!restore} onOpenChange={open=>!open&&setRestore(undefined)} title={`طلب استعادة ${restore?.backup_number||''}`}>
      <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800 space-y-2">
        <p>هذا <b>طلب مراجعة</b> وليس استعادة فورية لقاعدة البيانات.</p>
        <p>اكتب <b dir="ltr">RESTORE</b> حرفيًا. سيُنشأ Backup تلقائي للحالة الحالية قبل تسجيل الطلب.</p>
      </div>
      <div><Label>رمز التأكيد</Label><Input dir="ltr" value={confirmation} onChange={e=>setConfirmation(e.target.value)} placeholder="RESTORE"/></div>
      <div><Label>سبب الاستعادة (مطلوب)</Label><Textarea value={restoreNotes} onChange={e=>setRestoreNotes(e.target.value)} placeholder="مثال: استعادة بعد خطأ إدخال بتاريخ..."/></div>
      <Button type="button" variant="destructive" disabled={confirmation!=='RESTORE'||!restoreNotes.trim()} onClick={requestRestore}>تسجيل طلب الاستعادة (بدون تنفيذ DB)</Button>
    </FormDialog>
  </div>;
}
