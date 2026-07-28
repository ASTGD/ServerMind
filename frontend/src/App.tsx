import { BrowserRouter, Routes, Route, Navigate, useParams } from "react-router-dom"
import Layout from "@/components/layout/Layout"
import ProtectedRoute from "@/components/shared/ProtectedRoute"
import Dashboard from "@/routes/Dashboard"
import Servers from "@/routes/Servers"
import ServerDetail from "@/routes/ServerDetail"
import ServerOverview from "@/routes/ServerOverview"
import Playbooks from "@/routes/Playbooks"
import Runbooks from "@/routes/Runbooks"
import Dns from "@/routes/Dns"
import Deployments from "./routes/Deployments"
import Sites from "@/routes/Sites"
import PlaybookDetail from "@/routes/PlaybookDetail"
import ScriptGenerator from "@/routes/ScriptGenerator"
import MyScripts from "@/routes/MyScripts"
import Scheduler from "@/routes/Scheduler"
import FileManager from "@/routes/FileManager"
import Security from "@/routes/Security"
import ServerLogs from "./routes/ServerLogs"
import PublicStatusPage from "./routes/PublicStatus"
import Acknowledge from "./routes/Acknowledge"
import Backups from "@/routes/Backups"
import Installed from "@/routes/Installed"
import Hosting from "@/routes/Hosting"
import Logs from "@/routes/Logs"
import Missions from "@/routes/Missions"
import Reports from "@/routes/Reports"
import ServerReportView from "@/routes/ServerReportView"
import ClientReportView from "@/routes/ClientReportView"
import Team from "@/routes/Team"
import AcceptInvite from "@/routes/AcceptInvite"
import Settings from "@/routes/Settings"
import Dev from "@/routes/Dev"
import Auth from "@/routes/Auth"
import VerifyEmail from "@/routes/VerifyEmail"
import Claim from "@/routes/Claim"

/** Old per-mission log deep links now resolve to the mission's Missions detail pane. */
function MissionLogRedirect() {
  const { id } = useParams()
  return <Navigate to={`/missions/${id}`} replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/auth" element={<Auth />} />
        <Route path="/verify-email" element={<VerifyEmail />} />
        {/* Billing-provisioned accounts (WHMCS) set their first password here. */}
        <Route path="/claim" element={<Claim />} />
        {/* PUBLIC — no login. Strangers land here; the payload is an allowlist. */}
        <Route path="/status/:slug" element={<PublicStatusPage />} />
        {/* The link inside a page — unauthenticated, so it works from a phone that has
            never signed in. */}
        <Route path="/ack/:token" element={<Acknowledge />} />
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
            <Route path="logs" element={<ServerLogs />} />
            <Route path="backups" element={<Backups />} />
            <Route path="scheduler" element={<Scheduler />} />
            <Route path="hosting" element={<Hosting />} />
            <Route path="installed" element={<Installed />} />
          </Route>
          <Route path="playbooks" element={<Playbooks />} />
          <Route path="runbooks" element={<Runbooks />} />
          <Route path="sites" element={<Sites />} />
          <Route path="dns" element={<Dns />} />
          <Route path="deployments" element={<Deployments />} />
          <Route path="playbooks/:id" element={<PlaybookDetail />} />
          <Route path="scripts/generate" element={<ScriptGenerator />} />
          <Route path="scripts" element={<MyScripts />} />
          <Route path="logs" element={<Logs />} />
          {/* A mission's log now lives inside its Missions detail pane. */}
          <Route path="logs/mission/:id" element={<MissionLogRedirect />} />
          <Route path="missions" element={<Missions />} />
          <Route path="missions/:id" element={<Missions />} />
          <Route path="reports" element={<Reports />} />
          <Route path="reports/server/:serverId" element={<ServerReportView />} />
          <Route path="reports/client/:serverId" element={<ClientReportView />} />
          {/* A report opens inside the Reports page's detail pane (master-detail). */}
          <Route path="reports/:id" element={<Reports />} />
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
