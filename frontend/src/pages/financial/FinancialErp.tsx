import { useEffect, useMemo, useState } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { ArchiveRestore, BarChart3, Building2, FileSpreadsheet, Landmark, Link2, LogOut, Menu, Receipt, Scale, Users, WalletCards } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetTrigger } from '@/components/ui/sheet';
import { Skeleton } from '@/components/ui/skeleton';
import { Toaster } from '@/components/ui/toaster';
import { useToast } from '@/hooks/use-toast';
import { useBrand } from '@/lib/brand';
import { financialErpApi } from '@/lib/financialErpApi';
import { client } from '@/lib/localApi';
import { ROUTES } from '@/lib/routes';
import type { Company, PermissionMap, ServiceType } from '@/types/financialErp';
import { DashboardPage, ExpensesPage, RevenuesPage } from './FinancePages';
import { CompaniesPage, MemberLinksPage } from './MasterDataPages';
import { MonthlyPage, ReportsPage, SettlementsPage } from './OperationsPages';
import { BackupsPage } from './BackupsPage';

const sections=[
  {key:'dashboard',label:'لوحة المؤشرات',icon:BarChart3,permissions:['financial.dashboard.view']},
  {key:'companies',label:'الشركات والعقود',icon:Building2,permissions:['financial.companies.view']},
  {key:'links',label:'ارتباطات الأعضاء',icon:Link2,permissions:['financial.member_links.view']},
  {key:'monthly',label:'الإدخال الشهري',icon:FileSpreadsheet,permissions:['financial.monthly.view']},
  {key:'reports',label:'التقارير',icon:Receipt,permissions:['financial.reports.view']},
  {key:'settlements',label:'التسويات',icon:Scale,permissions:['financial.settlements.view']},
  {key:'revenues',label:'الإيرادات الفعلية',icon:Landmark,permissions:['financial.revenues.view']},
  {key:'expenses',label:'المصاريف',icon:WalletCards,permissions:['financial.expenses.view']},
  // أي صلاحية backups.* تُظهر القسم (كان يختفي إن وُجدت create دون view)
  {key:'backups',label:'النسخ الاحتياطية',icon:ArchiveRestore,permissions:['backups.view','backups.create','backups.download','backups.restore','backups.delete','backups.manage_restore_secret']},
] as const;

export default function FinancialErp(){
  const location=useLocation();const navigate=useNavigate();const {toast}=useToast();const {brand,resolveAssetUrl}=useBrand();
  const [permissions,setPermissions]=useState<PermissionMap>({});const [superAdmin,setSuperAdmin]=useState(false);
  const [companies,setCompanies]=useState<Company[]>([]);const [services,setServices]=useState<ServiceType[]>([]);
  const [ready,setReady]=useState(false);const [denied,setDenied]=useState(false);
  const can=(key:string)=>superAdmin||!!permissions[key];
  const finance=superAdmin||['financial.dashboard.view','financial.reports.view','financial.revenues.view','financial.settlements.view'].some(x=>permissions[x]);
  const notify=(error:unknown)=>toast({title:'تعذر إكمال العملية',description:error instanceof Error?error.message:'حدث خطأ غير متوقع',variant:'destructive'});
  const success=(message:string)=>toast({title:'تمت العملية بنجاح',description:message});
  const reloadCompanies=async()=>setCompanies((await financialErpApi.companies()).items);

  useEffect(()=>{(async()=>{try{
    const access=await financialErpApi.access();setPermissions(access.permissions||{});setSuperAdmin(access.is_super_admin);
    const [cmp,svc]=await Promise.all([financialErpApi.companies(),financialErpApi.serviceTypes(true)]);
    setCompanies(cmp.items);setServices(svc.items);setReady(true);
  }catch(e:any){if(e?.status===401||e?.status===403)setDenied(true);else notify(e)}})()},[]);

  const allowed=useMemo(
    ()=>sections.filter((x)=>x.permissions.some((p)=>can(p))),
    [permissions,superAdmin],
  );
  const tail=location.pathname.slice(ROUTES.ADMIN_FINANCIAL.length).split('/').filter(Boolean)[0];
  const requested=tail&&tail!=='legacy'?tail:'';
  const active=allowed.some(x=>x.key===requested)?requested:(allowed[0]?.key||'dashboard');
  useEffect(()=>{if(ready&&active!==requested)navigate(`${ROUTES.ADMIN_FINANCIAL}/${active}`,{replace:true})},[ready,active,requested]);
  const pageProps={companies,services,can,finance,notify,success};
  const content=active==='dashboard'?<DashboardPage {...pageProps}/>:active==='companies'?<CompaniesPage {...pageProps} reloadCompanies={reloadCompanies}/>:active==='links'?<MemberLinksPage {...pageProps}/>:active==='monthly'?<MonthlyPage {...pageProps}/>:active==='reports'?<ReportsPage {...pageProps}/>:active==='settlements'?<SettlementsPage {...pageProps}/>:active==='revenues'?<RevenuesPage {...pageProps}/>:active==='expenses'?<ExpensesPage {...pageProps}/>:active==='backups'?<BackupsPage can={can} notify={notify} success={success}/>:null;

  if(denied)return <div dir="rtl" className="min-h-screen grid place-items-center bg-slate-50"><div className="text-center space-y-3"><h1 className="font-bold text-xl">لا توجد صلاحية للإدارة المالية</h1><Button onClick={()=>navigate(ROUTES.ADMIN)}>العودة إلى إدارة العضويات</Button></div></div>;
  if(!ready)return <div dir="rtl" className="min-h-screen bg-slate-50 p-6 space-y-4"><Skeleton className="h-20"/><div className="grid grid-cols-4 gap-4"><Skeleton className="h-28"/><Skeleton className="h-28"/><Skeleton className="h-28"/><Skeleton className="h-28"/></div><Skeleton className="h-96"/></div>;
  return <div dir="rtl" className="min-h-screen print:bg-white" style={{background:'var(--mfec-bg,#f5f7fa)',color:'var(--mfec-text,#172033)'}}><Toaster/>
    <header className="text-white shadow-sm print:hidden" style={{background:brand.header_color||brand.primary_color||'var(--mfec-header)'}}>
      <div className="max-w-[1600px] mx-auto px-4 py-3 flex justify-between items-center gap-3">
        <div className="flex items-center gap-3"><img src={resolveAssetUrl(brand.system_logo)} alt={brand.org_abbr} className="w-12 h-12 object-contain"/><div><h1 className="font-bold text-xl">النظام المالي والإداري</h1><p className="text-xs opacity-80">{brand.system_name} · MFEC Financial ERP</p></div></div>
        <div className="flex gap-2"><Button variant="outline" className="bg-white/10 border-white/30 text-white hidden sm:flex" onClick={()=>navigate(ROUTES.ADMIN)}><Users className="w-4 h-4 ml-1"/>إدارة العضويات</Button><Button size="icon" variant="ghost" onClick={async()=>{await client.auth.logout();navigate(ROUTES.ADMIN_LOGIN)}}><LogOut className="w-5 h-5"/></Button></div>
      </div>
    </header>
    <div className="hidden print:flex items-center justify-between border-b-2 pb-3 mb-4">
      <div className="flex items-center gap-3"><img src={resolveAssetUrl(brand.report_logo||brand.system_logo)} alt="" className="w-16 h-16 object-contain"/><div><h1 className="font-bold text-xl">{brand.system_name}</h1><p>كشف مالي رسمي — MFEC</p></div></div>
      <div className="text-left text-sm"><p>تاريخ الإنشاء</p><b>{new Date().toLocaleDateString('en-GB')}</b></div>
    </div>
    <div className="max-w-[1600px] mx-auto p-3 md:p-5 lg:grid lg:grid-cols-[245px_minmax(0,1fr)] gap-5">
      <aside className="hidden lg:block border rounded-xl p-2 h-fit sticky top-4 print:hidden" style={{background:'var(--mfec-card,#fff)',borderColor:'var(--mfec-border,#d5dbe3)'}}><Nav allowed={allowed} active={active}/></aside>
      <div className="lg:hidden mb-3 print:hidden"><Sheet><SheetTrigger asChild><Button type="button" variant="outline"><Menu className="w-4 h-4 ml-2"/>أقسام النظام المالي</Button></SheetTrigger><SheetContent side="right" className="pt-12" dir="rtl"><Nav allowed={allowed} active={active}/></SheetContent></Sheet></div>
      <main key={active} className="min-w-0 space-y-4">{content}</main>
    </div>
  </div>;
}

function Nav({allowed,active}:{allowed:(typeof sections)[number][];active:string}){
  return <nav className="space-y-1"><p className="px-3 py-2 text-xs font-bold text-slate-400">مساحة العمل المالية</p>{allowed.map(({key,label,icon:Icon})=><Button key={key} type="button" asChild variant={active===key?'default':'ghost'} className="w-full justify-start" style={active===key?{background:'var(--mfec-active-nav,var(--mfec-button))',color:'#fff'}:undefined}><NavLink to={`${ROUTES.ADMIN_FINANCIAL}/${key}`}><Icon className="w-4 h-4 ml-2"/>{label}</NavLink></Button>)}</nav>;
}
