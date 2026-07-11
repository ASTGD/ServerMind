import { memo, type ReactNode } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { HighlightServerNames, type MentionServer } from "./serverMentions"

/**
 * The shared rich-text renderer for everything Ally SAYS — chat replies and (later) the
 * workspace. Turns Ally's markdown into readable, Claude-style output: headings, bold,
 * bullet/numbered lists, `code`, block quotes, and properly spaced paragraphs, at a
 * comfortable reading size.
 *
 * Safety: raw HTML is NOT rendered (no rehype-raw) — AI output can never inject markup;
 * remote images are dropped to just their alt text (no arbitrary image loads); links open
 * in a new tab with noopener and react-markdown's built-in URL sanitizer.
 *
 * Server names stay clickable INSIDE the prose: string children of text-bearing elements
 * are run through {@link HighlightServerNames}, so "restart nginx on TestServer4" still
 * chips TestServer4 — same behaviour as before, now inside formatted text.
 */
function MarkdownImpl({
  text,
  servers = [],
  onServerClick,
}: {
  text: string
  servers?: MentionServer[]
  onServerClick?: (id: string) => void
}) {
  // Wrap the string parts of a node's children in server-name chips; leave elements
  // (already-rendered <strong>, <code>, …) untouched. Not applied to code/links.
  const chip = (children: ReactNode): ReactNode => {
    if (!servers.length) return children
    const arr = Array.isArray(children) ? children : [children]
    return arr.map((c, i) =>
      typeof c === "string" ? (
        <HighlightServerNames key={i} text={c} servers={servers} onServerClick={onServerClick} />
      ) : (
        c
      ),
    )
  }

  return (
    // Color is inherited from the parent bubble so a success/failure bubble keeps its
    // green/red text; only structure + size are set here.
    <div className="ally-prose text-[15px] leading-[1.7]">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0">{chip(children)}</p>,
          h1: ({ children }) => <h3 className="mb-1.5 mt-3 text-base font-semibold first:mt-0">{chip(children)}</h3>,
          h2: ({ children }) => <h3 className="mb-1.5 mt-3 text-base font-semibold first:mt-0">{chip(children)}</h3>,
          h3: ({ children }) => <h4 className="mb-1 mt-2.5 text-[15px] font-semibold first:mt-0">{chip(children)}</h4>,
          ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5 first:mt-0 last:mb-0">{children}</ul>,
          ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5 first:mt-0 last:mb-0">{children}</ol>,
          li: ({ children }) => <li className="marker:text-muted-foreground">{chip(children)}</li>,
          strong: ({ children }) => <strong className="font-semibold">{chip(children)}</strong>,
          em: ({ children }) => <em>{chip(children)}</em>,
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer noopener"
              className="font-medium text-primary underline underline-offset-2 hover:opacity-80"
            >
              {children}
            </a>
          ),
          code: ({ className, children }) => {
            // Fenced block (has a language class or contains newlines) vs inline code.
            const isBlock = /language-/.test(className || "") || String(children).includes("\n")
            return isBlock ? (
              <code className="block overflow-x-auto whitespace-pre rounded-lg bg-muted p-3 font-mono text-[13px]">
                {children}
              </code>
            ) : (
              <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[13px]">{children}</code>
            )
          },
          pre: ({ children }) => <pre className="my-2 first:mt-0 last:mb-0">{children}</pre>,
          blockquote: ({ children }) => (
            <blockquote className="my-2 border-l-2 border-border pl-3 text-muted-foreground">{children}</blockquote>
          ),
          hr: () => <hr className="my-3 border-border" />,
          table: ({ children }) => (
            <div className="my-2 overflow-x-auto">
              <table className="w-full border-collapse text-sm">{children}</table>
            </div>
          ),
          th: ({ children }) => <th className="border border-border px-2 py-1 text-left font-semibold">{chip(children)}</th>,
          td: ({ children }) => <td className="border border-border px-2 py-1">{chip(children)}</td>,
          // Never load arbitrary remote images from AI output — show the alt text only.
          img: ({ alt }) => (alt ? <span className="text-muted-foreground">[{alt}]</span> : null),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  )
}

/** Memoized: re-rendering markdown on every parent tick is wasteful; text rarely changes. */
const Markdown = memo(MarkdownImpl)
export default Markdown
