/**
 * ProtectedRoute — autentifikatsiyasiz foydalanuvchilarni /login ga yo'naltiradi.
 *
 * Props:
 *   requiredRole — ixtiyoriy. Berilsa, faqat o'sha roldagi foydalanuvchi kiradi.
 *                  Superadmin uchun: requiredRole="superadmin" → /superadmin panel.
 *                  Boshqa rol → / ga yo'naltiradi (403 o'rniga).
 */

import { Navigate, Outlet, useLocation } from "react-router-dom";
import { Center, Loader } from "@mantine/core";
import { useAuth } from "./AuthContext";

interface ProtectedRouteProps {
  /** Agar berilsa — faqat o'sha rolga ruxsat */
  requiredRole?: string;
}

export function ProtectedRoute({ requiredRole }: ProtectedRouteProps) {
  const { user, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <Center h="100vh">
        <Loader size="lg" />
      </Center>
    );
  }

  if (!user) {
    // Joriy sahifani state'ga saqlaymiz — login'dan keyin qaytib kelish uchun
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // Rol tekshiruvi — mos kelmasa bosh sahifaga
  if (requiredRole && user.role !== requiredRole) {
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
}
