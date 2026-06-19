/**
 * ProtectedRoute — autentifikatsiyasiz foydalanuvchilarni /login ga yo'naltiradi.
 */

import { Navigate, Outlet, useLocation } from "react-router-dom";
import { Center, Loader } from "@mantine/core";
import { useAuth } from "./AuthContext";

export function ProtectedRoute() {
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

  return <Outlet />;
}
