import { Toaster } from '@/components/ui/sonner';
import { TooltipProvider } from '@/components/ui/tooltip';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { BrandProvider } from '@/lib/brand';
import { ROUTES, legacyAdminToCanonical } from '@/lib/routes';
import Index from './pages/Index';
import AdminDashboard from './pages/AdminDashboard';
import UsersManagement from './pages/UsersManagement';
import AdminLogin from './pages/AdminLogin';
import AuthCallback from './pages/AuthCallback';
import AuthError from './pages/AuthError';
import PrintMembers from './pages/PrintMembers';
import BrandSettings from './pages/BrandSettings';
import FormSettings from './pages/FormSettings';
import MembershipReport from './pages/MembershipReport';
import FinancialActivities from './pages/FinancialActivities';
// MODULE_IMPORTS_START
// MODULE_IMPORTS_END

const queryClient = new QueryClient();

/** Redirect old `/admin` and `/admin/*` URLs to `/iraq-ecom-traders/admin/*`. */
function LegacyAdminRedirect() {
  const location = useLocation();
  return (
    <Navigate
      to={legacyAdminToCanonical(location.pathname, location.search, location.hash)}
      replace
    />
  );
}

const AppRoutes = () => (
  <Routes>
    {/* Canonical routes */}
    <Route path={ROUTES.REGISTRATION} element={<Index />} />
    <Route path={ROUTES.ADMIN_LOGIN} element={<AdminLogin />} />
    <Route path={ROUTES.ADMIN} element={<AdminDashboard />} />
    <Route path={ROUTES.ADMIN_PRINT} element={<PrintMembers />} />
    <Route path={ROUTES.ADMIN_USERS} element={<UsersManagement />} />
    <Route path={ROUTES.ADMIN_BRAND_SETTINGS} element={<BrandSettings />} />
    <Route path={ROUTES.ADMIN_FORM_SETTINGS} element={<FormSettings />} />
    <Route path={ROUTES.ADMIN_MEMBERSHIP_REPORT} element={<MembershipReport />} />
    <Route path={ROUTES.ADMIN_FINANCIAL} element={<FinancialActivities />} />
    <Route path="/auth/callback" element={<AuthCallback />} />
    <Route path="/auth/error" element={<AuthError />} />

    {/* Legacy redirects */}
    <Route path="/" element={<Navigate to={ROUTES.REGISTRATION} replace />} />
    <Route path="/admin" element={<LegacyAdminRedirect />} />
    <Route path="/admin/*" element={<LegacyAdminRedirect />} />

    {/* MODULE_ROUTES_START */}
    {/* MODULE_ROUTES_END */}

    {/* Unknown paths → registration (Atoms 404 placeholder is disabled in vite.config) */}
    <Route path="*" element={<Navigate to={ROUTES.REGISTRATION} replace />} />
  </Routes>
);

const App = () => (
  <QueryClientProvider client={queryClient}>
    <BrandProvider>
      {/* MODULE_PROVIDERS_START */}
      {/* MODULE_PROVIDERS_END */}
      <TooltipProvider>
        <Toaster />
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </TooltipProvider>
      {/* MODULE_PROVIDERS_CLOSE */}
    </BrandProvider>
  </QueryClientProvider>
);

export default App;
export { AppRoutes };
