import { Navigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";

export function RequireAuth({ children }: { children: JSX.Element }) {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) return null; // or a spinner
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return children;
}
