import { Navigate, useParams } from "react-router-dom"

/**
 * The site page used to live inside the server's address. Anyone who bookmarked one, or
 * was sent one, still lands somewhere — changing where a page lives should not break the
 * links people already have.
 */
export default function SiteRedirect() {
  const { siteId = "" } = useParams()
  return <Navigate to={`/sites/${siteId}`} replace />
}
