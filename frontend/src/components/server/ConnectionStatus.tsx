import type { Server } from "@/types"
import { useTranslation } from "react-i18next"
import { cn } from "@/lib/utils"

interface Props {
  status: Server["status"]
  className?: string
}

const statusConfig = {
  online: { dot: "bg-green-500", label: "status.online" },
  offline: { dot: "bg-red-500", label: "status.offline" },
  unknown: { dot: "bg-muted-foreground", label: "status.unknown" },
} as const

export default function ConnectionStatus({ status, className }: Props) {
  const { t } = useTranslation()
  const cfg = statusConfig[status] ?? statusConfig.unknown

  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs font-medium", className)}>
      <span className={cn("h-2 w-2 rounded-full", cfg.dot)} />
      {t(`servers.${cfg.label}`)}
    </span>
  )
}
