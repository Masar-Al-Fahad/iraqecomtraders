import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ROUTES } from '@/lib/routes';

export default function AuthCallback() {
  const navigate = useNavigate();

  useEffect(() => {
    // Local mode: OIDC callback is unused — send user to local admin login
    navigate(ROUTES.ADMIN_LOGIN, { replace: true });
  }, [navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
        <p className="text-gray-600">جاري التحويل لتسجيل الدخول المحلي...</p>
      </div>
    </div>
  );
}
