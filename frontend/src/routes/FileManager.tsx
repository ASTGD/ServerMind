import { useEffect, useRef, useCallback, useState, useMemo } from "react"
import { useParams, useOutletContext } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import Editor from "@monaco-editor/react"
import {
  Folder,
  FolderOpen,
  FileText,
  FileCode,
  Terminal,
  Settings,
  Database,
  ImageIcon,
  Archive,
  File,
  ChevronRight,
  FolderPlus,
  Upload,
  Download,
  Trash2,
  Pencil,
  X,
  Save,
  Loader2,
  AlertTriangle,
  Eye,
  EyeOff,
  ArrowLeft,
  HardDrive,
  Sparkles,
  ShieldCheck,
} from "lucide-react"
import {
  listDirectory,
  readFile,
  writeFile,
  makeDirectory,
  deletePath,
  renamePath,
  uploadFile,
  type FileEntry,
} from "@/api/files"
import { apiClient } from "@/api/client"
import { usePublishPageContext } from "@/hooks/usePageContext"
import { redactSecrets } from "@/lib/redactSecrets"
import { format } from "date-fns"

// ── Helpers ────────────────────────────────────────────────────────────────

function fmtSize(bytes: number | null): string {
  if (bytes == null) return "—"
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`
}

function FileIcon({ entry }: { entry: FileEntry }) {
  if (entry.type === "dir") return <Folder className="h-4 w-4 text-yellow-400 shrink-0" />

  const ext = entry.name.split(".").pop()?.toLowerCase() ?? ""
  const CODE = new Set(["js","ts","jsx","tsx","py","rb","go","rs","php","java","c","cpp","h","cs","lua","swift","kt","scala"])
  const SHELL = new Set(["sh","bash","zsh","fish","ps1","bat","cmd"])
  const CFG = new Set(["conf","config","cfg","ini","yaml","yml","toml","env","htaccess","nginx"])
  const DB = new Set(["sql","db","sqlite"])
  const IMG = new Set(["png","jpg","jpeg","gif","svg","ico","webp","bmp"])
  const ARC = new Set(["zip","tar","gz","bz2","xz","7z","rar"])
  const TXT = new Set(["txt","md","rst","log","csv","tsv"])

  if (CODE.has(ext)) return <FileCode className="h-4 w-4 text-blue-400 shrink-0" />
  if (SHELL.has(ext)) return <Terminal className="h-4 w-4 text-green-400 shrink-0" />
  if (CFG.has(ext)) return <Settings className="h-4 w-4 text-orange-400 shrink-0" />
  if (DB.has(ext)) return <Database className="h-4 w-4 text-violet-400 shrink-0" />
  if (IMG.has(ext)) return <ImageIcon className="h-4 w-4 text-pink-400 shrink-0" />
  if (ARC.has(ext)) return <Archive className="h-4 w-4 text-amber-400 shrink-0" />
  if (TXT.has(ext)) return <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
  return <File className="h-4 w-4 text-muted-foreground shrink-0" />
}

function monacoLang(filename: string): string {
  const ext = filename.split(".").pop()?.toLowerCase() ?? ""
  const MAP: Record<string, string> = {
    js: "javascript", ts: "typescript", jsx: "javascript", tsx: "typescript",
    py: "python", rb: "ruby", go: "go", rs: "rust", php: "php",
    java: "java", c: "c", cpp: "cpp", h: "c", cs: "csharp",
    sh: "shell", bash: "shell", zsh: "shell", ps1: "powershell",
    yml: "yaml", yaml: "yaml", toml: "ini", ini: "ini", cfg: "ini", conf: "ini",
    json: "json", xml: "xml", html: "html", css: "css", scss: "scss",
    sql: "sql", md: "markdown", txt: "plaintext", env: "ini", log: "plaintext",
    nginx: "nginx",
  }
  return MAP[ext] ?? "plaintext"
}

function buildCrumbs(path: string): { label: string; path: string }[] {
  const parts = path.split("/").filter(Boolean)
  const crumbs: { label: string; path: string }[] = [{ label: "/", path: "/" }]
  parts.forEach((p, i) => {
    crumbs.push({ label: p, path: "/" + parts.slice(0, i + 1).join("/") })
  })
  return crumbs
}

// ── InlineDialog ───────────────────────────────────────────────────────────

interface InlineDialogProps {
  title: string
  placeholder: string
  initial?: string
  isPending: boolean
  onConfirm: (value: string) => void
  onCancel: () => void
}

function InlineDialog({ title, placeholder, initial = "", isPending, onConfirm, onCancel }: InlineDialogProps) {
  const [val, setVal] = useState(initial)
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-card border border-border rounded-xl shadow-2xl w-full max-w-sm p-5 space-y-4">
        <h3 className="font-semibold text-foreground">{title}</h3>
        <input
          autoFocus
          type="text"
          value={val}
          onChange={(e) => setVal(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && val.trim()) onConfirm(val.trim()) }}
          placeholder={placeholder}
          className="w-full rounded-lg border border-border bg-background text-sm text-foreground px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary/40"
        />
        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground border border-border rounded-lg hover:bg-muted/50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => val.trim() && onConfirm(val.trim())}
            disabled={!val.trim() || isPending}
            className="flex items-center gap-1.5 px-4 py-1.5 text-sm font-medium bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            {isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            OK
          </button>
        </div>
      </div>
    </div>
  )
}

// ── FileManager ────────────────────────────────────────────────────────────

export default function FileManager() {
  const { id: serverId } = useParams<{ id: string }>()
  const { openAI } = useOutletContext<{ openAI: (seed?: string) => void }>()
  const qc = useQueryClient()

  // Navigation state
  const [currentPath, setCurrentPath] = useState("/")
  const [showHidden, setShowHidden] = useState(false)

  // Editor state
  const [selectedFile, setSelectedFile] = useState<FileEntry | null>(null)
  const [editContent, setEditContent] = useState("")
  const [isDirty, setIsDirty] = useState(false)

  // Dialog state
  const [mkdirOpen, setMkdirOpen] = useState(false)
  const [renameEntry, setRenameEntry] = useState<FileEntry | null>(null)

  // Upload
  const uploadInputRef = useRef<HTMLInputElement>(null)
  const [uploadPct, setUploadPct] = useState<number | null>(null)

  // Error banner
  const [bannerErr, setBannerErr] = useState<string | null>(null)

  // ── Queries ────────────────────────────────────────────────────────────

  const listKey = ["files-dir", serverId, currentPath, showHidden]

  const {
    data: listing,
    isLoading: listLoading,
    isError: listError,
    error: listErrObj,
  } = useQuery({
    queryKey: listKey,
    queryFn: () => listDirectory(serverId!, currentPath, showHidden),
    enabled: !!serverId,
    retry: 1,
  })

  const {
    data: fileContent,
    isLoading: fileLoading,
  } = useQuery({
    queryKey: ["file-content", serverId, selectedFile?.path],
    queryFn: () => readFile(serverId!, selectedFile!.path),
    enabled: !!selectedFile && selectedFile.type === "file",
    retry: false,
  })

  // Sync file content into editor when it loads
  useEffect(() => {
    if (fileContent) {
      setEditContent(fileContent.content)
      setIsDirty(false)
    }
  }, [fileContent])

  // Surface list errors in the banner
  useEffect(() => {
    if (listError && listErrObj) {
      setBannerErr((listErrObj as Error).message ?? "Failed to list directory")
    }
  }, [listError, listErrObj])

  // ── Mutations ──────────────────────────────────────────────────────────

  const invalidateDir = () =>
    qc.invalidateQueries({ queryKey: ["files-dir", serverId, currentPath] })

  const writeMut = useMutation({
    mutationFn: () => writeFile(serverId!, selectedFile!.path, editContent),
    onSuccess: () => { setIsDirty(false); invalidateDir() },
    onError: (e: Error) => setBannerErr(e.message),
  })

  const mkdirMut = useMutation({
    mutationFn: (name: string) => {
      const target = currentPath === "/"
        ? `/${name}`
        : `${currentPath}/${name}`
      return makeDirectory(serverId!, target)
    },
    onSuccess: () => { setMkdirOpen(false); invalidateDir() },
    onError: (e: Error) => setBannerErr(e.message),
  })

  const deleteMut = useMutation({
    mutationFn: (path: string) => deletePath(serverId!, path),
    onSuccess: (_data, path) => {
      if (selectedFile?.path === path) setSelectedFile(null)
      invalidateDir()
    },
    onError: (e: Error) => setBannerErr(e.message),
  })

  const renameMut = useMutation({
    mutationFn: ({ oldPath, newName }: { oldPath: string; newName: string }) => {
      const dir = oldPath.lastIndexOf("/") > 0
        ? oldPath.substring(0, oldPath.lastIndexOf("/"))
        : "/"
      const newPath = dir === "/" ? `/${newName}` : `${dir}/${newName}`
      return renamePath(serverId!, oldPath, newPath)
    },
    onSuccess: () => { setRenameEntry(null); invalidateDir() },
    onError: (e: Error) => setBannerErr(e.message),
  })

  const uploadMut = useMutation({
    mutationFn: (file: File) => uploadFile(serverId!, currentPath, file, setUploadPct),
    onSuccess: () => { setUploadPct(null); invalidateDir() },
    onError: (e: Error) => { setUploadPct(null); setBannerErr(e.message) },
  })

  // ── Handlers ───────────────────────────────────────────────────────────

  const navigate = (path: string) => {
    if (isDirty && !window.confirm("You have unsaved changes. Discard and navigate away?")) return
    setCurrentPath(path)
    setSelectedFile(null)
    setEditContent("")
    setIsDirty(false)
    setBannerErr(null)
  }

  const openEntry = (entry: FileEntry) => {
    if (entry.type === "dir") {
      navigate(entry.path)
      return
    }
    if (isDirty && !window.confirm("Discard unsaved changes?")) return
    setSelectedFile(entry)
    setEditContent("")
    setIsDirty(false)
  }

  const closeEditor = () => {
    if (isDirty && !window.confirm("Discard unsaved changes?")) return
    setSelectedFile(null)
    setIsDirty(false)
  }

  const handleDownload = useCallback(
    async (entry: FileEntry) => {
      try {
        const res = await apiClient.get<Blob>(`/api/servers/${serverId}/files/download`, {
          params: { path: entry.path },
          responseType: "blob",
        })
        const url = URL.createObjectURL(res.data)
        const a = document.createElement("a")
        a.href = url
        a.download = entry.name
        a.click()
        URL.revokeObjectURL(url)
      } catch (e) {
        setBannerErr((e as Error).message)
      }
    },
    [serverId],
  )

  const handleUploadChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) uploadMut.mutate(file)
    e.target.value = ""
  }

  // Context C2 — "Ask Ally about this file": publish the OPEN text file as page context
  // so Ally can explain/review it. Secrets are redacted in the BROWSER first — a
  // wp-config password never reaches the AI prompt. (Same page-context pipeline the
  // My Scripts page uses.)
  const fileForAlly = useMemo(() => {
    const isText = !!selectedFile && selectedFile.type === "file" && !fileContent?.is_binary
    if (!isText || !fileContent) return null
    const { text, count } = redactSecrets(editContent.slice(0, 200_000))
    const body = text.length > 8000 ? text.slice(0, 8000) + "\n…(truncated)" : text
    return {
      count,
      ctx: {
        label: `File: ${selectedFile!.name}`,
        context:
          "The user is looking at a file on their server in the File Manager.\n" +
          `Path: ${selectedFile!.path}\n` +
          "Any passwords, keys and tokens were hidden before you saw this — never ask the user to reveal them.\n" +
          "--- FILE START ---\n" +
          body +
          "\n--- FILE END ---",
        templates: [
          "What does this file do?",
          "Is anything here unsafe or wrong?",
          "Explain this file in simple words",
        ],
      },
    }
  }, [selectedFile, fileContent, editContent])

  usePublishPageContext(fileForAlly?.ctx ?? null)

  // ── Render ─────────────────────────────────────────────────────────────

  const crumbs = buildCrumbs(currentPath)
  const editorOpen = !!selectedFile && selectedFile.type === "file"

  return (
    <>
      {/* Full-bleed container that cancels the p-6 from Layout */}
      <div className="-m-6 flex flex-col" style={{ height: "calc(100vh - 57px)" }}>

        {/* ── Toolbar ── */}
        <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-b border-border bg-card shrink-0">
          {/* Breadcrumb */}
          <div className="flex items-center gap-1 text-sm min-w-0 overflow-hidden">
            <HardDrive className="h-4 w-4 text-muted-foreground shrink-0 mr-0.5" />
            {crumbs.map((c, i) => (
              <span key={c.path} className="flex items-center gap-0.5 min-w-0 shrink-0">
                {i > 0 && <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />}
                <button
                  onClick={() => navigate(c.path)}
                  className={`truncate max-w-[120px] hover:text-primary transition-colors ${
                    i === crumbs.length - 1
                      ? "text-foreground font-medium"
                      : "text-muted-foreground"
                  }`}
                >
                  {c.label}
                </button>
              </span>
            ))}
            {listLoading && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground ml-1 shrink-0" />}
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-1 shrink-0">
            {currentPath !== "/" && (
              <button
                onClick={() => navigate(listing?.parent_path ?? "/")}
                title="Up one level"
                className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
              >
                <ArrowLeft className="h-4 w-4" />
              </button>
            )}
            <button
              onClick={() => setShowHidden((v) => !v)}
              title={showHidden ? "Hide hidden files" : "Show hidden files"}
              className={`p-1.5 rounded-lg transition-colors hover:bg-muted/60 ${
                showHidden ? "text-primary" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {showHidden ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
            </button>
            <button
              onClick={() => setMkdirOpen(true)}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium border border-border text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
            >
              <FolderPlus className="h-3.5 w-3.5" />
              New Folder
            </button>
            <button
              onClick={() => uploadInputRef.current?.click()}
              disabled={uploadMut.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-60 transition-colors"
            >
              {uploadMut.isPending ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  {uploadPct != null ? `${uploadPct}%` : "Uploading…"}
                </>
              ) : (
                <>
                  <Upload className="h-3.5 w-3.5" />
                  Upload
                </>
              )}
            </button>
            <input
              ref={uploadInputRef}
              type="file"
              className="hidden"
              onChange={handleUploadChange}
            />
          </div>
        </div>

        {/* ── Error banner ── */}
        {bannerErr && (
          <div className="flex items-center justify-between gap-3 px-4 py-2 bg-red-500/10 border-b border-red-500/20 text-sm text-red-400 shrink-0">
            <span className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              {bannerErr}
            </span>
            <button onClick={() => setBannerErr(null)} className="hover:text-red-300 transition-colors">
              <X className="h-4 w-4" />
            </button>
          </div>
        )}

        {/* ── Body ── */}
        <div className="flex flex-1 overflow-hidden">

          {/* File list panel */}
          <div
            className={`flex flex-col overflow-y-auto border-r border-border transition-all ${
              editorOpen ? "w-72 shrink-0" : "flex-1"
            }`}
          >
            {!listLoading && listing?.entries.length === 0 && (
              <div className="flex flex-col items-center justify-center flex-1 py-20 gap-3 text-muted-foreground">
                <FolderOpen className="h-10 w-10 opacity-20" />
                <span className="text-sm">Empty directory</span>
              </div>
            )}

            {!listLoading && !listing && !listError && (
              <div className="flex items-center justify-center flex-1 gap-2 text-muted-foreground text-sm">
                <Loader2 className="h-5 w-5 animate-spin" />
                Connecting…
              </div>
            )}

            {(listing?.entries?.length ?? 0) > 0 && (
              <table className="w-full text-sm table-fixed">
                <thead className="sticky top-0 z-10 bg-card border-b border-border">
                  <tr>
                    <th className="text-left px-4 py-2 text-[11px] font-medium text-muted-foreground">
                      Name
                    </th>
                    {!editorOpen && (
                      <>
                        <th className="text-right px-4 py-2 text-[11px] font-medium text-muted-foreground w-24">
                          Size
                        </th>
                        <th className="text-right px-4 py-2 text-[11px] font-medium text-muted-foreground w-36 hidden lg:table-cell">
                          Modified
                        </th>
                        <th className="text-right px-4 py-2 text-[11px] font-medium text-muted-foreground w-28 hidden xl:table-cell">
                          Perms
                        </th>
                      </>
                    )}
                    <th className="w-24 shrink-0" />
                  </tr>
                </thead>
                <tbody>
                  {listing!.entries.map((entry) => (
                    <tr
                      key={entry.path}
                      onClick={() => openEntry(entry)}
                      className={`group cursor-pointer border-b border-border/30 hover:bg-muted/30 transition-colors ${
                        selectedFile?.path === entry.path ? "bg-primary/5 hover:bg-primary/5" : ""
                      }`}
                    >
                      {/* Name */}
                      <td className="px-4 py-2 min-w-0">
                        <div className="flex items-center gap-2 min-w-0">
                          <FileIcon entry={entry} />
                          <span
                            className={`truncate ${
                              entry.type === "dir"
                                ? "font-medium text-foreground"
                                : "text-foreground/90"
                            }`}
                          >
                            {entry.name}
                          </span>
                          {entry.type === "link" && (
                            <span className="text-[9px] border border-border rounded px-1 text-muted-foreground shrink-0">
                              link
                            </span>
                          )}
                        </div>
                      </td>

                      {!editorOpen && (
                        <>
                          <td className="px-4 py-2 text-right text-xs text-muted-foreground">
                            {entry.type === "dir" ? "—" : fmtSize(entry.size)}
                          </td>
                          <td className="px-4 py-2 text-right text-xs text-muted-foreground hidden lg:table-cell">
                            {entry.modified
                              ? format(new Date(entry.modified), "MMM d, HH:mm")
                              : "—"}
                          </td>
                          <td className="px-4 py-2 text-right font-mono text-[10px] text-muted-foreground hidden xl:table-cell">
                            {entry.permissions}
                          </td>
                        </>
                      )}

                      {/* Row actions */}
                      <td className="px-2 py-1.5">
                        <div className="flex items-center justify-end gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                          {entry.type !== "dir" && (
                            <button
                              title="Download"
                              onClick={(e) => { e.stopPropagation(); void handleDownload(entry) }}
                              className="p-1.5 rounded text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
                            >
                              <Download className="h-3.5 w-3.5" />
                            </button>
                          )}
                          <button
                            title="Rename"
                            onClick={(e) => { e.stopPropagation(); setRenameEntry(entry) }}
                            className="p-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                          <button
                            title="Delete"
                            onClick={(e) => {
                              e.stopPropagation()
                              if (
                                window.confirm(
                                  `Delete "${entry.name}"${entry.type === "dir" ? " and all its contents" : ""}?`
                                )
                              ) {
                                deleteMut.mutate(entry.path)
                              }
                            }}
                            className="p-1.5 rounded text-muted-foreground hover:text-red-400 hover:bg-red-500/10 transition-colors"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* ── Editor panel ── */}
          {editorOpen && (
            <div className="flex-1 flex flex-col overflow-hidden min-w-0">
              {/* Editor toolbar */}
              <div className="flex items-center justify-between gap-3 px-4 py-2 border-b border-border bg-card shrink-0">
                <div className="flex items-center gap-2 min-w-0">
                  <FileIcon entry={selectedFile} />
                  <span className="text-sm text-foreground font-medium truncate min-w-0">
                    {selectedFile.path}
                  </span>
                  {isDirty && (
                    <span className="text-[10px] text-orange-400 border border-orange-500/30 bg-orange-500/5 rounded px-1.5 py-0.5 shrink-0">
                      unsaved
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {fileForAlly && (
                    <>
                      {fileForAlly.count > 0 && (
                        <span
                          className="hidden items-center gap-1 text-[10px] text-muted-foreground sm:flex"
                          title="Passwords and keys are hidden before Ally sees this file"
                        >
                          <ShieldCheck className="h-3 w-3 text-emerald-500" />
                          {fileForAlly.count} hidden
                        </span>
                      )}
                      <button
                        onClick={() => openAI()}
                        title="Ask Ally about this file — passwords and keys are hidden first"
                        className="flex items-center gap-1.5 rounded-lg bg-brand-gradient-r px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90"
                      >
                        <Sparkles className="h-3.5 w-3.5" />
                        Ask Ally
                      </button>
                    </>
                  )}
                  {!fileContent?.is_binary && (
                    <button
                      onClick={() => writeMut.mutate()}
                      disabled={!isDirty || writeMut.isPending}
                      className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
                    >
                      {writeMut.isPending
                        ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        : <Save className="h-3.5 w-3.5" />
                      }
                      Save
                    </button>
                  )}
                  <button
                    onClick={closeEditor}
                    className="p-1 rounded text-muted-foreground hover:text-foreground transition-colors"
                    title="Close editor"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              </div>

              {/* Monaco or loading */}
              {fileLoading ? (
                <div className="flex items-center justify-center flex-1 gap-2 text-muted-foreground text-sm">
                  <Loader2 className="h-5 w-5 animate-spin" />
                  Loading file…
                </div>
              ) : (
                <div className="flex-1 overflow-hidden">
                  <Editor
                    height="100%"
                    language={monacoLang(selectedFile.name)}
                    value={editContent}
                    onChange={(v) => {
                      setEditContent(v ?? "")
                      setIsDirty(true)
                    }}
                    theme="vs-dark"
                    options={{
                      readOnly: fileContent?.is_binary ?? false,
                      minimap: { enabled: false },
                      scrollBeyondLastLine: false,
                      fontSize: 13,
                      lineNumbers: "on",
                      wordWrap: "off",
                      padding: { top: 12, bottom: 12 },
                      scrollbar: { alwaysConsumeMouseWheel: false },
                      renderLineHighlight: "line",
                    }}
                  />
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── New Folder dialog ── */}
      {mkdirOpen && (
        <InlineDialog
          title="New Folder"
          placeholder="folder-name"
          isPending={mkdirMut.isPending}
          onConfirm={(name) => mkdirMut.mutate(name)}
          onCancel={() => setMkdirOpen(false)}
        />
      )}

      {/* ── Rename dialog ── */}
      {renameEntry && (
        <InlineDialog
          title={`Rename "${renameEntry.name}"`}
          placeholder="new-name"
          initial={renameEntry.name}
          isPending={renameMut.isPending}
          onConfirm={(newName) => renameMut.mutate({ oldPath: renameEntry.path, newName })}
          onCancel={() => setRenameEntry(null)}
        />
      )}
    </>
  )
}
