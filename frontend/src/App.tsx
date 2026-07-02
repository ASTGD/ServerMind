import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom"
import Layout from "@/components/layout/Layout"
import ProtectedRoute from "@/components/shared/ProtectedRoute"
import Dashboard from "@/routes/Dashboard"
import Servers from "@/routes/Servers"
import ServerDetail from "@/routes/ServerDetail"
import ServerOverview from "@/routes/ServerOverview"
import Assistant from "@/routes/Assistant"
import Playbooks from "@/routes/Playbooks"
import PlaybookDetail from "@/routes/PlaybookDetail"
import ScriptGenerator from "@/routes/ScriptGenerator"
import MyScripts from "@/routes/MyScripts"
import Scheduler from "@/routes/Scheduler"
import FileManager from "@/routes/FileManager"
import Security from "@/routes/Security"
import Backups from "@/routes/Backups"
import Installed from "@/routes/Installed"
import Hosting from "@/routes/Hosting"
import Logs from "@/routes/Logs"
import Team from "@/routes/Team"
import AcceptInvite from "@/routes/AcceptInvite"
import Settings from "@/routes/Settings"
import Auth from "@/routes/Auth"
import VerifyEmail from "@/routes/VerifyEmail"

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/auth" element={<Auth />} />
        <Route path="/verify-email" element={<VerifyEmail />} />
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
          <Route path="assistant" element={<Assistant />} />
          {/* The terminal workspace is rendered by Layout (persistent); this route just
              exists so navigation + the sidebar active state work. */}
          <Route path="terminal" element={<div />} />
          <Route path="servers" element={<Servers />} />
          <Route path="servers/:id" element={<ServerDetail />}>
            <Route index element={<ServerOverview />} />
            <Route path="files" element={<FileManager />} />
            <Route path="security" element={<Security />} />
            <Route path="backups" element={<Backups />} />
            <Route path="scheduler" element={<Scheduler />} />
            <Route path="hosting" element={<Hosting />} />
            <Route path="installed" element={<Installed />} />
          </Route>
          <Route path="playbooks" element={<Playbooks />} />
          <Route path="playbooks/:id" element={<PlaybookDetail />} />
          <Route path="scripts/generate" element={<ScriptGenerator />} />
          <Route path="scripts" element={<MyScripts />} />
          <Route path="logs" element={<Logs />} />
          <Route path="team" element={<Team />} />
          <Route path="team/accept/:token" element={<AcceptInvite />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
