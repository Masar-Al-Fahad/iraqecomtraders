import type { ReactNode } from 'react';
import { FileUp, Loader2, Search } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';

export const money=(value:number|string|undefined)=>`${Number(value||0).toLocaleString('ar-IQ',{maximumFractionDigits:3})} د.ع`;
export const statusLabel=(value:string)=>({
  active:'فعال',inactive:'غير فعال',suspended:'معلق',ended:'منتهي',draft:'مسودة',
  approved:'معتمد',settled:'تم التحاسب',unsettled:'غير محاسب',reversed:'معكوس',
}[value]||value);

export function StatusBadge({value}:{value:string}){
  const good=['active','approved','settled'].includes(value);
  return <Badge variant={good?'default':'outline'} className={value==='reversed'||value==='ended'?'text-red-700 border-red-300':''}>{statusLabel(value)}</Badge>;
}

export function PageTitle({title,description,actions}:{title:string;description:string;actions?:ReactNode}){
  return <div className="flex items-start justify-between gap-3 flex-wrap">
    <div><h2 className="text-xl font-bold text-slate-900">{title}</h2><p className="text-sm text-slate-500 mt-1">{description}</p></div>
    {actions&&<div className="flex gap-2 flex-wrap">{actions}</div>}
  </div>;
}

export function SearchBox({value,onChange,placeholder='بحث...'}:{value:string;onChange:(value:string)=>void;placeholder?:string}){
  return <div className="relative min-w-56"><Search className="absolute right-3 top-3 w-4 h-4 text-slate-400"/><Input className="pr-9" value={value} onChange={e=>onChange(e.target.value)} placeholder={placeholder}/></div>;
}

export function Loading({label='جاري تحميل البيانات...'}:{label?:string}){
  return <Card><CardContent className="p-12 text-center text-slate-500"><Loader2 className="w-7 h-7 animate-spin mx-auto mb-3"/>{label}</CardContent></Card>;
}

export function Empty({title='لا توجد بيانات',description='غيّر الفلاتر أو أضف أول سجل.'}:{title?:string;description?:string}){
  return <div className="p-12 text-center"><p className="font-bold text-slate-700">{title}</p><p className="text-sm text-slate-500 mt-1">{description}</p></div>;
}

export function FormDialog({open,onOpenChange,title,children,className='max-w-3xl'}:{open:boolean;onOpenChange:(open:boolean)=>void;title:string;children:ReactNode;className?:string}){
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className={`${className} max-h-[90vh] overflow-y-auto`} dir="rtl"><DialogHeader><DialogTitle>{title}</DialogTitle></DialogHeader>{children}</DialogContent></Dialog>;
}

export function FileButton({label='رفع مرفق',accept='.pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png,.webp',onFile,disabled}:{label?:string;accept?:string;onFile:(file:File)=>Promise<void>;disabled?:boolean}){
  return <Button variant="outline" disabled={disabled} asChild><label className="cursor-pointer"><FileUp className="w-4 h-4 ml-2"/>{label}<input className="hidden" type="file" accept={accept} onChange={async e=>{const file=e.target.files?.[0];if(file)await onFile(file);e.currentTarget.value='';}}/></label></Button>;
}

export function CompactTable({headers,children}:{headers:string[];children:ReactNode}){
  return <div className="overflow-auto rounded-xl border bg-white"><table className="w-full text-sm whitespace-nowrap"><thead className="bg-slate-100 text-slate-700"><tr>{headers.map(x=><th key={x} className="p-3 text-right font-semibold">{x}</th>)}</tr></thead><tbody>{children}</tbody></table></div>;
}
