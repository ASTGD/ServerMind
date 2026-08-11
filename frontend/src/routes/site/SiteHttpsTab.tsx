import { useOutletContext } from "react-router-dom"
import type { SiteDetail } from "@/api/sites"
import Http3Toggle from "@/components/sites/Http3Toggle"
import InstallCertificate from "@/components/sites/InstallCertificate"
import SigningRequest from "@/components/sites/SigningRequest"
import SiteHttps from "@/components/sites/SiteHttps"

/**
 * The HTTPS page: the free certificate first, the one you already have second.
 *
 * Only this page carries the paste form — the Overview keeps the single free button, because
 * the overview is where somebody goes to get a site working, and two ways to do one job side
 * by side makes the simple one look like a decision.
 */
export default function SiteHttpsTab() {
  const { site } = useOutletContext<{ site: SiteDetail }>()
  return (
    <div className="space-y-4">
      <SiteHttps siteId={site.id} domain={site.domain} hasSsl={site.has_ssl} />
      <InstallCertificate siteId={site.id} domain={site.domain} />
      <SigningRequest siteId={site.id} domain={site.domain} />
      <Http3Toggle siteId={site.id} />
    </div>
  )
}
