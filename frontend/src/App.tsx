import { Toaster } from '@/components/ui/sonner';
import { TooltipProvider } from '@/components/ui/tooltip';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { BrandProvider } from '@/lib/brand';
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
// MODULE_IMPORTS_START
// MODULE_IMPORTS_END

const queryClient = new QueryClient();

const AppRoutes = () => (
  <Routes>
    <Route path="/" element={<Index />} />
    <Route path="/admin/login" element={<AdminLogin />} />
    <Route path="/admin" element={<AdminDashboard />} />
    <Route path="/admin/print" element={<PrintMembers />} />
    <Route path="/admin/users" element={<UsersManagement />} />
    <Route path="/admin/brand-settings" element={<BrandSettings />} />
    <Route path="/admin/form-settings" element={<FormSettings />} />
    <Route path="/admin/membership-report" element={<MembershipReport />} />
    <Route path="/auth/callback" element={<AuthCallback />} />
    <Route path="/auth/error" element={<AuthError />} />
    {/* MODULE_ROUTES_START */}
    {/* MODULE_ROUTES_END */}
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
