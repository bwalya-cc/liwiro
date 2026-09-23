import type { ReactNode } from "react"

type WorkspaceLayoutProps = {
  eyebrow?: string
  title: string
  description?: string
  topActions?: ReactNode
  stackPanels?: boolean
  systemTitle?: string
  systemDescription?: string
  editorTitle?: string
  editorDescription?: string
  modeToggle?: ReactNode
  systemPanel: ReactNode
  editorPanel: ReactNode
}

export function WorkspaceLayout({
  eyebrow,
  title,
  description,
  topActions,
  stackPanels = false,
  systemTitle = "Overview",
  systemDescription,
  editorTitle = "Details",
  editorDescription,
  modeToggle,
  systemPanel,
  editorPanel,
}: WorkspaceLayoutProps) {
  return (
    <div className="workspace-page">
      <header className="workspace-page-header">
        <div className="min-w-0">
          {eyebrow ? <p className="workspace-eyebrow">{eyebrow}</p> : null}
          <h1 className="workspace-title">{title}</h1>
          {description ? <p className="workspace-copy">{description}</p> : null}
        </div>
        {topActions ? <div className="workspace-header-actions">{topActions}</div> : null}
      </header>

      <div className="workspace-grid">
        <section className={`workspace-column workspace-system-column ${stackPanels ? "lg:col-span-2" : ""}`}>
          <div className="workspace-panel-head">
            <div>
              <p className="workspace-panel-label">{systemTitle}</p>
              {systemDescription ? <p className="workspace-panel-copy">{systemDescription}</p> : null}
            </div>
          </div>
          <div className="workspace-panel-body">{systemPanel}</div>
        </section>

        <section className={`workspace-column workspace-editor-column ${stackPanels ? "lg:col-span-2" : ""}`}>
          <div className="workspace-panel-head workspace-editor-head">
            <div>
              <p className="workspace-panel-label">{editorTitle}</p>
              {editorDescription ? <p className="workspace-panel-copy">{editorDescription}</p> : null}
            </div>
            {modeToggle ? <div className="workspace-mode-slot">{modeToggle}</div> : null}
          </div>
          <div className="workspace-panel-body workspace-editor-body">{editorPanel}</div>
        </section>
      </div>
    </div>
  )
}
