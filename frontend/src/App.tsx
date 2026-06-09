import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom"
import Layout from "@/components/layout/Layout"
import ProtectedRoute from "@/components/shared/ProtectedRoute"
import Dashboard from "@/routes/Dashboard"
import Servers from "@/routes/Servers"
import ServerDetail from "@/routes/ServerDetail"
import Chat from "@/routes/Chat"
import Terminal from "@/routes/Terminal"
import Playbooks from "@/routes/Playbooks"
import PlaybookDetail from "@/routes/PlaybookDetail"
import ScriptGenerator from "@/routes/ScriptGenerator"
import MyScripts from "@/routes/MyScripts"
import Scheduler from "@/routes/Scheduler"
import FileManager from "@/routes/FileManager"
import Monitoring from "@/routes/Monitoring"
import Security from "@/routes/Security"
import Backups from "@/routes/Backups"
import Hosting from "@/routes/Hosting"
import Logs from "@/routes/Logs"
import Team from "@/routes/Team"
import AcceptInvite from "@/routes/AcceptInvite"
import Settings from "@/routes/Settings"
import Auth from "@/routes/Auth"

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/auth" element={<Auth />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="servers" element={<Servers />} />
          <Route path="servers/:id" element={<ServerDetail />} />
          <Route path="servers/:id/chat" element={<Chat />} />
          <Route path="servers/:id/terminal" element={<Terminal />} />
          <Route path="playbooks" element={<Playbooks />} />
          <Route path="playbooks/:id" element={<PlaybookDetail />} />
          <Route path="scripts/generate" element={<ScriptGenerator />} />
          <Route path="scripts" element={<MyScripts />} />
          <Route path="servers/:id/scheduler" element={<Scheduler />} />
          <Route path="servers/:id/files" element={<FileManager />} />
          <Route path="servers/:id/monitoring" element={<Monitoring />} />
          <Route path="servers/:id/security" element={<Security />} />
          <Route path="servers/:id/backups" element={<Backups />} />
          <Route path="servers/:id/hosting" element={<Hosting />} />
          <Route path="logs" element={<Logs />} />
          <Route path="team" element={<Team />} />
          <Route path="team/accept/:token" element={<AcceptInvite />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
