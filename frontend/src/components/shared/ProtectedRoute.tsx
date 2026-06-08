import { Navigate, useLocation } from "react-router-dom"
import { useAuthStore } from "@/store/authStore"

interface Props {
  children: React.ReactNode
}

/** Redirects to /auth if the user is not authenticated. */
export default function ProtectedRoute({ children }: Props) {
  const token = useAuthStore((s) => s.token)
  const location = useLocation()

  if (!token) {
    return <Navigate to="/auth" state={{ from: location }} replace />
  }

  return <>{children}</>
}
