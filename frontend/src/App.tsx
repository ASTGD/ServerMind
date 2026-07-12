import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom"
import Layout from "@/components/layout/Layout"
import ProtectedRoute from "@/components/shared/ProtectedRoute"
import Dashboard from "@/routes/Dashboard"
import Servers from "@/routes/Servers"
import ServerDetail from "@/routes/ServerDetail"
import ServerOverview from "@/routes/ServerOverview"
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
import Missions from "@/routes/Missions"
import Team from "@/routes/Team"
import AcceptInvite from "@/routes/AcceptInvite"
import Settings from "@/routes/Settings"
import Dev from "@/routes/Dev"
import Auth from "@/routes/Auth"
import VerifyEmail from "@/routes/VerifyEmail"
import Claim from "@/routes/Claim"

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/auth" element={<Auth />} />
        <Route path="/verify-email" element={<VerifyEmail />} />
        {/* Billing-provisioned accounts (WHMCS) set their first password here. */}
        <Route path="/claim" element={<Claim />} />
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
          {/* Ally is now ONE window (opened from the sidebar icon, rendered by Layout),
              not a page — old /assistant links fall back to the dashboard. */}
          <Route path="assistant" element={<Navigate to="/dashboard" replace />} />
          {/* The terminal is now a floating window (opened from the sidebar dock / top-bar
              icon), not a page — old /terminal links fall back to the dashboard. */}
          <Route path="terminal" element={<Navigate to="/dashboard" replace />} />
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
          <Route path="missions" element={<Missions />} />
          <Route path="team" element={<Team />} />
          <Route path="team/accept/:token" element={<AcceptInvite />} />
          <Route path="settings" element={<Settings />} />
          {/* Admin-only Dev Door (docs/EVAL-DRIVEN-DEV.md) — the page itself guards on
              is_admin; the backend /api/dev/* routes 403 a non-admin regardless. */}
          <Route path="dev" element={<Dev />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
