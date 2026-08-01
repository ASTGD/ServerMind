import { useOutletContext } from "react-router-dom"
import type { SiteDetail } from "@/api/sites"
import SiteHttps from "@/components/sites/SiteHttps"

export default function SiteHttpsTab() {
  const { site } = useOutletContext<{ site: SiteDetail }>()
  return <SiteHttps siteId={site.id} domain={site.domain} hasSsl={site.has_ssl} />
}
