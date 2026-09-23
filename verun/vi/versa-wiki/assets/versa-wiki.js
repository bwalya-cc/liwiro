const body = document.body
const referencePath = body.dataset.reference || "./versa-reference.json"
const eyebrow = body.dataset.eyebrow || "Canonical Versa Wiki"
const loadEyebrow = body.dataset.loadEyebrow || "Versa Wiki"
const app = document.getElementById("app")

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
}

function highlightVersa(source, highlighting) {
  const config = highlighting || {}
  const keywords = new Set(config.keywords || [])
  const builtins = new Set(config.builtins || [])
  const constants = new Set(config.constants || [])
  const text = String(source ?? "")
  let i = 0
  let html = ""

  const isIdentifierStart = (ch) => /[A-Za-z_]/.test(ch)
  const isIdentifierPart = (ch) => /[A-Za-z0-9_]/.test(ch)

  while (i < text.length) {
    const ch = text[i]

    if (ch === "#") {
      let end = text.indexOf("\n", i)
      if (end === -1) end = text.length
      html += `<span class="tok-comment">${escapeHtml(text.slice(i, end))}</span>`
      i = end
      continue
    }

    if (ch === "'" || ch === "\"" || ch === "`") {
      const quote = ch
      let end = i + 1
      while (end < text.length) {
        const current = text[end]
        if (current === "\\") {
          end += 2
          continue
        }
        if (current === quote) {
          end += 1
          break
        }
        end += 1
      }
      html += `<span class="tok-string">${escapeHtml(text.slice(i, end))}</span>`
      i = end
      continue
    }

    if (/[0-9]/.test(ch)) {
      let end = i + 1
      while (end < text.length && /[0-9._eE+-]/.test(text[end])) end += 1
      html += `<span class="tok-number">${escapeHtml(text.slice(i, end))}</span>`
      i = end
      continue
    }

    if (isIdentifierStart(ch)) {
      let end = i + 1
      while (end < text.length && isIdentifierPart(text[end])) end += 1
      const token = text.slice(i, end)
      const escaped = escapeHtml(token)
      if (keywords.has(token)) {
        html += `<span class="tok-keyword">${escaped}</span>`
      } else if (builtins.has(token)) {
        html += `<span class="tok-builtin">${escaped}</span>`
      } else if (constants.has(token)) {
        html += `<span class="tok-constant">${escaped}</span>`
      } else {
        html += escaped
      }
      i = end
      continue
    }

    html += escapeHtml(ch)
    i += 1
  }

  return html
}

function renderExampleCards(items, heading, className, highlighting) {
  if (!Array.isArray(items) || items.length === 0) return ""
  const cards = items.map((item) => {
    const title = escapeHtml(item.title || "Example")
    const code = Array.isArray(item.code) ? item.code.join("\n") : String(item.code || "")
    const notes = Array.isArray(item.notes) ? item.notes : []
    return `
      <article class="example-card ${className}">
        <header><h3>${title}</h3></header>
        <pre><code class="language-versa">${highlightVersa(code, highlighting)}</code></pre>
        ${notes.length ? `<div class="notes"><ul>${notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("")}</ul></div>` : ""}
      </article>
    `
  }).join("")
  return `
    <div class="example-grid">
      <div class="meta-card">
        <h3>${escapeHtml(heading)}</h3>
      </div>
      ${cards}
    </div>
  `
}

function renderBulletCard(title, items) {
  if (!Array.isArray(items) || items.length === 0) return ""
  return `
    <section class="meta-card">
      <h3>${escapeHtml(title)}</h3>
      <ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </section>
  `
}

function renderSourceCards(items) {
  if (!Array.isArray(items) || items.length === 0) return ""
  return `
    <section class="meta-card">
      <h2>Sources</h2>
      <ul>
        ${items.map((item) => {
          const path = escapeHtml(item.path || "")
          const purpose = escapeHtml(item.purpose || "")
          return `<li><strong>${path}</strong>${purpose ? `<br/>${purpose}` : ""}</li>`
        }).join("")}
      </ul>
    </section>
  `
}

function renderTables(tables) {
  if (!Array.isArray(tables) || tables.length === 0) return ""
  return tables.map((table) => `
    <section class="table-wrap">
      ${table.title ? `<h3>${escapeHtml(table.title)}</h3>` : ""}
      <table>
        <thead>
          <tr>${(table.columns || []).map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr>
        </thead>
        <tbody>
          ${(table.rows || []).map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`).join("")}
        </tbody>
      </table>
    </section>
  `).join("")
}

function renderErrors(errors) {
  if (!Array.isArray(errors) || errors.length === 0) return ""
  return `
    <div class="error-list">
      ${errors.map((item) => `
        <article class="error-card">
          <h3>${escapeHtml(item.errorContains || "Error pattern")}</h3>
          <p>${escapeHtml(item.meaning || "")}</p>
          ${(item.fix || []).length ? `<ul>${item.fix.map((fixLine) => `<li>${escapeHtml(fixLine)}</li>`).join("")}</ul>` : ""}
        </article>
      `).join("")}
    </div>
  `
}

function renderPage(data) {
  const sections = Array.isArray(data.sections) ? data.sections : []
  const highlighting = data.highlighting || {}
  const coverage = data.coverage || {}
  const sectionGroups = Array.isArray(data.sectionGroups) ? data.sectionGroups : []
  const sidebarLinks = sections.map((section) => `
    <a href="#${escapeHtml(section.id)}" data-search="${escapeHtml(`${section.title} ${section.summary || ""} ${(section.tags || []).join(" ")} ${(section.constructs || []).join(" ")} ${(section.queryHints || []).join(" ")} ${(section.domains || []).join(" ")} ${section.group || ""}`.toLowerCase())}">
      <span class="toc-title">${escapeHtml(section.title)}</span>
      <span class="toc-summary">${escapeHtml(section.summary || "")}</span>
    </a>
  `).join("")

  const sectionHtml = sections.map((section, index) => `
    <article class="section" id="${escapeHtml(section.id)}">
      <div class="section-header">
        <div class="section-index">Section ${index + 1}</div>
        ${section.group ? `<div class="section-index">${escapeHtml(section.group)}</div>` : ""}
        ${Array.isArray(section.domains) && section.domains.length ? `<div class="section-index">${escapeHtml(section.domains.join(" / "))}</div>` : ""}
        <h2>${escapeHtml(section.title)}</h2>
        <p>${escapeHtml(section.summary || "")}</p>
      </div>
      ${renderBulletCard("Constructs", section.constructs)}
      ${renderBulletCard("Query Hints", section.queryHints)}
      ${renderBulletCard("Syntax Patterns", section.syntaxPatterns)}
      ${renderBulletCard("Tags", section.tags)}
      ${(section.rules || []).length ? `<div class="meta-card"><h3>Rules</h3><ul>${section.rules.map((rule) => `<li>${escapeHtml(rule)}</li>`).join("")}</ul></div>` : ""}
      ${renderTables(section.tables)}
      ${renderErrors(section.errors)}
      ${renderExampleCards(section.validExamples, "Valid Examples", "", highlighting)}
      ${renderExampleCards(section.invalidExamples, "Invalid Examples", "invalid", highlighting)}
    </article>
  `).join("")

  app.innerHTML = `
    <div class="shell">
      <header class="hero">
        <p class="eyebrow">${escapeHtml(eyebrow)}</p>
        <h1>${escapeHtml(data.title || "Versa Reference")}</h1>
        <p>${escapeHtml(data.summary || "")}</p>
        <div class="hero-meta">
          <span class="pill">Updated ${escapeHtml(data.version || "unknown")}</span>
          <span class="pill">${escapeHtml(data.canonicalPath || "")}</span>
          <span class="pill">${escapeHtml(data.htmlPath || "")}</span>
        </div>
      </header>
      <div class="layout">
        <aside class="sidebar">
          <input id="search" class="search" type="search" placeholder="Filter sections, rules, and examples" />
          <nav class="toc" id="toc">${sidebarLinks}</nav>
          ${sectionGroups.length ? `
            <section class="meta-card">
              <h2>Reference Areas</h2>
              <ul>${sectionGroups.map((group) => `<li><strong>${escapeHtml(group.title || group.id || "")}</strong>${group.description ? `<br/>${escapeHtml(group.description)}` : ""}</li>`).join("")}</ul>
            </section>
          ` : ""}
          <section class="meta-card">
            <h2>Agent Usage</h2>
            <ul>${(data.agentUsage?.priorityRules || []).map((rule) => `<li>${escapeHtml(rule)}</li>`).join("")}</ul>
          </section>
          <section class="meta-card">
            <h2>Generation Checklist</h2>
            <ul>${(data.agentUsage?.generationChecklist || []).map((rule) => `<li>${escapeHtml(rule)}</li>`).join("")}</ul>
          </section>
          ${renderBulletCard("Whole-Script Workflow", data.agentUsage?.sourceConstructionWorkflow || [])}
          ${renderBulletCard("Missing-Info Policy", data.agentUsage?.missingInfoPolicy || [])}
          ${renderBulletCard("Parser-Verified Behaviors", coverage.parserVerifiedBehaviors || [])}
          ${renderBulletCard("Style Guidance", coverage.styleGuidance || [])}
          ${renderBulletCard("Known High-Risk Areas", coverage.knownHighRiskAreas || [])}
          ${renderBulletCard("Documented Modules", coverage.documentedModules || [])}
          ${renderBulletCard("Runtime Globals", coverage.runtimeGlobals || [])}
          ${renderSourceCards(data.sources || [])}
        </aside>
        <main class="content-panel">
          ${sectionHtml}
        </main>
      </div>
    </div>
  `

  const search = document.getElementById("search")
  const links = Array.from(document.querySelectorAll(".toc a"))
  const articles = Array.from(document.querySelectorAll(".section"))

  search?.addEventListener("input", () => {
    const needle = String(search.value || "").trim().toLowerCase()
    let visibleCount = 0
    links.forEach((link, index) => {
      const article = articles[index]
      const text = `${link.dataset.search || ""} ${article?.textContent || ""}`.toLowerCase()
      const visible = !needle || text.includes(needle)
      link.style.display = visible ? "" : "none"
      if (article) article.style.display = visible ? "" : "none"
      if (visible) visibleCount += 1
    })

    let empty = document.querySelector(".empty-state")
    if (!visibleCount) {
      if (!empty) {
        empty = document.createElement("div")
        empty.className = "empty-state"
        empty.textContent = "No sections matched that search."
        document.querySelector(".content-panel")?.appendChild(empty)
      }
    } else if (empty) {
      empty.remove()
    }
  })

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      const id = entry.target.getAttribute("id")
      const link = document.querySelector(`.toc a[href="#${id}"]`)
      if (!link) return
      if (entry.isIntersecting) {
        document.querySelectorAll(".toc a.active").forEach((node) => node.classList.remove("active"))
        link.classList.add("active")
      }
    })
  }, { rootMargin: "-30% 0px -55% 0px", threshold: 0.1 })

  articles.forEach((article) => observer.observe(article))
}

async function boot() {
  try {
    const response = await fetch(referencePath)
    if (!response.ok) {
      throw new Error(`Failed to load ${referencePath}: ${response.status}`)
    }
    const data = await response.json()
    renderPage(data)
  } catch (error) {
    app.innerHTML = `
      <div class="shell">
        <div class="hero">
          <p class="eyebrow">${escapeHtml(loadEyebrow)}</p>
          <h1>Unable to load the reference JSON</h1>
          <p>${escapeHtml(error.message)}</p>
          <p>Open <code>${escapeHtml(referencePath)}</code> directly or serve this folder over a local static file server.</p>
        </div>
      </div>
    `
  }
}

boot()
