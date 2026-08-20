import type { ComponentProps, ReactNode } from 'react';
import { FileUp, Loader2, Search } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';

/** Western digits 0-9 only (display). Does not change stored values. */
export const formatLatn=(value:number|string|undefined,opts?:Intl.NumberFormatOptions)=>
  Number(value||0).toLocaleString('en-US',{maximumFractionDigits:3,...opts});
export const money=(value:number|string|undefined)=>`${formatLatn(value)} د.ع`;
export const statusLabel=(value:string)=>({
  active:'فعال',inactive:'غير فعال',suspended:'معلق',ended:'منتهي',draft:'مسودة',
  approved:'معتمد',settled:'تم التحاسب',unsettled:'غير محاسب',reversed:'معكوس',
  ready:'جاهزة',restore_requested:'طلب استعادة',deleted:'محذوفة',cancelled:'ملغى',
}[value]||value);

export function StatusBadge({value}:{value:string}){
  const good=['active','approved','settled'].includes(value);
  return <Badge variant={good?'default':'outline'} className={value==='reversed'||value==='ended'||value==='cancelled'?'text-red-700 border-red-300':''}>{statusLabel(value)}</Badge>;
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
  return <Button type="button" variant="outline" disabled={disabled} asChild><label className="cursor-pointer"><FileUp className="w-4 h-4 ml-2"/>{label}<input className="hidden" type="file" accept={accept} onChange={async e=>{const file=e.target.files?.[0];if(file)await onFile(file);e.currentTarget.value='';}}/></label></Button>;
}

/** Native date input that can never submit a form or mutate client routing on Enter. */
export function SafeDateInput(props:Omit<ComponentProps<typeof Input>,'type'>){
  return <Input {...props} type="date" onKeyDown={event=>{
    event.stopPropagation();
    if(event.key==='Enter')event.preventDefault();
    props.onKeyDown?.(event);
  }}/>;
}

export function CompactTable({headers,children,printFriendly=false}:{headers:(string|ReactNode)[];children:ReactNode;printFriendly?:boolean}){
  return <div className={`rounded-xl border bg-[var(--mfec-card,#fff)] ${printFriendly?'overflow-visible print:overflow-visible':'overflow-auto'}`} style={{borderColor:'var(--mfec-border,#d5dbe3)'}}>
    <table className={`w-full text-sm ${printFriendly?'print:text-[10px] print:whitespace-normal whitespace-normal':'whitespace-nowrap'}`}>
      <thead style={{background:'var(--mfec-table-header,#1e506b)',color:'#fff'}}><tr>{headers.map((x,i)=><th key={i} className="p-3 text-right font-semibold">{x}</th>)}</tr></thead>
      <tbody className="[&>tr:nth-child(even)]:bg-[var(--mfec-table-alt,#F3F4F6)]">{children}</tbody>
    </table>
  </div>;
}

/** Compact icon+label action button matching membership-admin style. */
export function ActionButton({
  label,
  icon: Icon,
  onClick,
  title,
  variant = 'outline',
  disabled,
  className = '',
}: {
  label: string;
  icon?: React.ComponentType<{ className?: string }>;
  onClick?: () => void;
  title?: string;
  variant?: 'outline' | 'ghost' | 'destructive' | 'default';
  disabled?: boolean;
  className?: string;
}) {
  return (
    <Button
      type="button"
      size="sm"
      variant={variant}
      disabled={disabled}
      title={title || label}
      onClick={onClick}
      className={`h-8 px-2 text-xs gap-1 border ${className}`}
      style={
        variant === 'default'
          ? { background: 'var(--mfec-button)', borderColor: 'var(--mfec-button)', color: '#fff' }
          : { borderColor: 'var(--mfec-border,#d5dbe3)' }
      }
    >
      {Icon ? <Icon className="w-3.5 h-3.5" /> : null}
      {label}
    </Button>
  );
}
