import fs from "fs/promises"
import path from "path"

import { WorkspaceLayout } from "@/components/ide/workspace-layout"
import { CopyIconButton } from "@/components/ui/copy-icon-button"

async function readFirstExistingFile(paths) {
  for (const filePath of paths) {
    try {
      return await fs.readFile(filePath, "utf8")
    } catch (error) {
      if (error?.code !== "ENOENT") {
        throw error
      }
    }
  }

  throw new Error(`None of the expected files exist: ${paths.join(", ")}`)
}

async function readRepositoryLicense() {
  const repoRoot = path.resolve(process.cwd(), "..", "..")
  const [licenseText, noticeText] = await Promise.all([
    fs.readFile(path.join(repoRoot, "LICENSE"), "utf8"),
    readFirstExistingFile([
      path.join(repoRoot, "LICENSE_NOTICE.md"),
      path.join(repoRoot, "docs", "legal", "license-notice.md"),
    ]),
  ])
  return { licenseText, noticeText }
}

export default async function LicensePage() {
  const { licenseText, noticeText } = await readRepositoryLicense()

  return (
    <WorkspaceLayout
      eyebrow="License"
      title="Open-source license"
      description="Repository licensing, attribution, and the full license text displayed directly in the workspace."
      systemTitle="License Summary"
      systemDescription="Primary license type and attribution details for this repository."
      editorTitle="License Text"
      editorDescription="Full source text from the repository license files."
      systemPanel={
        <div className="space-y-4">
          <div className="rounded-[1.25rem] border border-white/10 bg-white/5 p-4">
            <p className="app-stat-label">License Type</p>
            <p className="mt-2 text-2xl font-semibold text-white">MIT</p>
            <p className="mt-2 text-sm text-slate-400">Copyright (c) 2026 Bwalya Cameron Chishimba</p>
          </div>
          <div className="rounded-[1.25rem] border border-white/10 bg-white/5 p-4">
            <p className="app-stat-label">Repository Notice</p>
            <div className="relative mt-3">
              <CopyIconButton
                text={noticeText}
                label="Copy repository notice"
                successMessage="Repository notice copied"
                errorMessage="Failed to copy repository notice"
                className="absolute right-3 top-3 border-white/10 bg-slate-950/90 text-slate-100 hover:bg-slate-900 hover:text-white"
              />
              <pre className="overflow-x-auto whitespace-pre-wrap rounded-2xl border border-white/10 bg-[rgba(5,12,20,0.96)] p-4 text-xs leading-6 text-slate-200">
                {noticeText}
              </pre>
            </div>
          </div>
        </div>
      }
      editorPanel={
        <div className="relative rounded-[1.45rem] border border-white/10 bg-[rgba(5,12,20,0.96)] p-4 shadow-[0_24px_52px_rgba(2,6,23,0.28)]">
          <CopyIconButton
            text={licenseText}
            label="Copy license text"
            successMessage="License text copied"
            errorMessage="Failed to copy license text"
            className="absolute right-4 top-4 border-white/10 bg-slate-950/90 text-slate-100 hover:bg-slate-900 hover:text-white"
          />
          <pre className="overflow-x-auto whitespace-pre-wrap text-sm leading-7 text-slate-100">{licenseText}</pre>
        </div>
      }
    />
  )
}
