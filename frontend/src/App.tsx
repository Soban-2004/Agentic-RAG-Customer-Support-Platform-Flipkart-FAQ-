import { Navigate, Route, Routes } from "react-router-dom"
import { useAuth } from "./hooks/useAuth"
import { Login } from "./pages/Login"
import { Signup } from "./pages/Signup"
import { Chat } from "./pages/Chat"
import { Demo } from "./pages/Demo"

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return null
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      {/* Unauthenticated on purpose -- see Demo.tsx / src/api/demo_ws.py */}
      <Route path="/demo" element={<Demo />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Chat />
          </ProtectedRoute>
        }
      />
      <Route
        path="/chat/:threadId"
        element={
          <ProtectedRoute>
            <Chat />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
