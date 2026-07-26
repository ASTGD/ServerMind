import { useQuery } from "@tanstack/react-query"
import IncidentsPanel from "./IncidentsPanel"
import { listIncidents } from "@/api/escalation"

/**
 * The dashboard's incident strip. Renders nothing at all when nothing is escalating —
 * a permanent "no incidents" card would train the eye to skip the one place that must
 * never be skipped.
 */
export default function ActiveIncidentsBanner() {
  const { data: incidents = [] } = useQuery({
    queryKey: ["incidents", "active"],
    queryFn: () => listIncidents("active"),
    refetchInterval: 30_000,
  })
  if (incidents.length === 0) return null
  return <IncidentsPanel compact />
}
