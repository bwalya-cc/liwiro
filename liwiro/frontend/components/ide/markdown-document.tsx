import type { ReactNode } from "react"

import Link from "next/link"

import { CopyIconButton } from "@/components/ui/copy-icon-button"

function slugify(value: string) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
}

function withPrefix(id: string, prefix = "") {
  const safeId = slugify(id)
  const safePrefix = slugify(prefix)
  if (safePrefix && safeId) return `${safePrefix}-${safeId}`
  return safePrefix || safeId || "section"
}

function renderInline(text: string, keyBase: string) {
  const parts = String(text || "").split(/(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))/g)
  return parts.filter(Boolean).map((part, index) => {
    const key = `${keyBase}-${index}`
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={key}>{part.slice(1, -1)}</code>
    }
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={key}>{part.slice(2, -2)}</strong>
    }
    const linkMatch = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/)
    if (linkMatch) {
      const href = linkMatch[2]
      const isInternal = href.startsWith("/") || href.startsWith("#")
      if (href.startsWith("/")) {
        return (
          <Link key={key} href={href}>
            {linkMatch[1]}
          </Link>
        )
      }
      if (href.startsWith("#")) {
        return (
          <a key={key} href={href}>
            {linkMatch[1]}
          </a>
        )
      }
      return (
        <a key={key} href={href} target={isInternal ? undefined : "_blank"} rel={isInternal ? undefined : "noreferrer"}>
          {linkMatch[1]}
        </a>
      )
    }
    return <span key={key}>{part}</span>
  })
}

type ParsedBlock =
  | { type: "heading"; level: number; text: string; id: string }
  | { type: "paragraph"; text: string }
  | { type: "list"; ordered: boolean; items: string[] }
  | { type: "code"; language: string; content: string }

function parseMarkdown(content: string): ParsedBlock[] {
  const blocks: ParsedBlock[] = []
  const lines = String(content || "").replace(/\r\n/g, "\n").split("\n")
  let index = 0

  while (index < lines.length) {
    const line = lines[index]
    const trimmed = line.trim()

    if (!trimmed) {
      index += 1
      continue
    }

    const headingMatch = trimmed.match(/^(#{1,6})\s+(.*)$/)
    if (headingMatch) {
      blocks.push({
        type: "heading",
        level: headingMatch[1].length,
        text: headingMatch[2].trim(),
        id: slugify(headingMatch[2]),
      })
      index += 1
      continue
    }

    const codeMatch = trimmed.match(/^```(.*)$/)
    if (codeMatch) {
      const language = codeMatch[1].trim()
      const codeLines: string[] = []
      index += 1
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        codeLines.push(lines[index])
        index += 1
      }
      if (index < lines.length) index += 1
      blocks.push({ type: "code", language, content: codeLines.join("\n") })
      continue
    }

    const unorderedMatch = trimmed.match(/^[-*+]\s+(.*)$/)
    if (unorderedMatch) {
      const items: string[] = []
      while (index < lines.length) {
        const next = lines[index].trim()
        const match = next.match(/^[-*+]\s+(.*)$/)
        if (!match) break
        items.push(match[1].trim())
        index += 1
      }
      blocks.push({ type: "list", ordered: false, items })
      continue
    }

    const orderedMatch = trimmed.match(/^\d+\.\s+(.*)$/)
    if (orderedMatch) {
      const items: string[] = []
      while (index < lines.length) {
        const next = lines[index].trim()
        const match = next.match(/^\d+\.\s+(.*)$/)
        if (!match) break
        items.push(match[1].trim())
        index += 1
      }
      blocks.push({ type: "list", ordered: true, items })
      continue
    }

    const paragraphLines: string[] = []
    while (index < lines.length) {
      const next = lines[index]
      const nextTrimmed = next.trim()
      if (!nextTrimmed) break
      if (/^(#{1,6})\s+/.test(nextTrimmed) || /^```/.test(nextTrimmed) || /^[-*+]\s+/.test(nextTrimmed) || /^\d+\.\s+/.test(nextTrimmed)) {
        break
      }
      paragraphLines.push(nextTrimmed)
      index += 1
    }
    blocks.push({ type: "paragraph", text: paragraphLines.join(" ") })
  }

  return blocks
}

export function extractMarkdownHeadings(content: string, minLevel = 1, maxLevel = 3, idPrefix = "") {
  return parseMarkdown(content)
    .filter((block): block is Extract<ParsedBlock, { type: "heading" }> => block.type === "heading")
    .filter((block) => block.level >= minLevel && block.level <= maxLevel)
    .map((block) => ({ ...block, id: withPrefix(block.id, idPrefix) }))
}

export function MarkdownDocument({ content, className = "", idPrefix = "" }: { content: string; className?: string; idPrefix?: string }) {
  const blocks = parseMarkdown(content)

  return (
    <div className={`markdown-content ${className}`.trim()}>
      {blocks.map((block, index) => {
        if (block.type === "heading") {
          const headingId = withPrefix(block.id, idPrefix)
          if (block.level === 1) {
            return <h1 key={`${headingId}-${index}`} id={headingId}>{block.text}</h1>
          }
          if (block.level === 2) {
            return <h2 key={`${headingId}-${index}`} id={headingId}>{block.text}</h2>
          }
          return <h3 key={`${headingId}-${index}`} id={headingId}>{block.text}</h3>
        }

        if (block.type === "paragraph") {
          return <p key={`paragraph-${index}`}>{renderInline(block.text, `paragraph-${index}`)}</p>
        }

        if (block.type === "list") {
          const Tag = block.ordered ? "ol" : "ul"
          return (
            <Tag key={`list-${index}`}>
              {block.items.map((item, itemIndex) => (
                <li key={`list-${index}-${itemIndex}`}>{renderInline(item, `list-${index}-${itemIndex}`)}</li>
              ))}
            </Tag>
          )
        }

        return (
          <pre key={`code-${index}`} className="relative">
            <CopyIconButton
              text={block.content}
              label="Copy code block"
              successMessage="Code block copied"
              errorMessage="Failed to copy code block"
              className="absolute right-3 top-3"
            />
            <code className="block">{block.content}</code>
          </pre>
        )
      })}
    </div>
  )
}
