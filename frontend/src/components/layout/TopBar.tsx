import { useTranslation } from "react-i18next"

export default function TopBar() {
  const { t } = useTranslation()

  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-card px-6">
      <div />
      <div className="flex items-center gap-4">
        <span className="text-sm text-muted-foreground">{t("app.tagline")}</span>
      </div>
    </header>
  )
}
