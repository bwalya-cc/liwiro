// SDK and guided-builder values become readable command text before execution.
export function vdbCommandText(payload) {
  if (typeof payload === "string") {
    const text = payload.trim()
    if (!text || /^[{[]/.test(text)) throw new Error("Use a command such as read users or read collection orders")
    return text
  }
  if (Array.isArray(payload)) return payload.map(vdbCommandText).join(";\n")
  if (payload?.commands) return payload.commands.map(vdbCommandText).join(";\n")
  const { action, ...fields } = payload || {}
  if (!action) throw new Error("A VDB command is required")
  const take = (key, fallback = "") => { const value = fields[key] ?? fallback; delete fields[key]; return value }
  const quote = (value) => typeof value === "string" && /^[A-Za-z_][A-Za-z0-9_.-]*$/.test(value) ? value : JSON.stringify(value)
  const valueText = (value) => Array.isArray(value) ? `[${value.map(valueText).join(", ")}]` : value && typeof value === "object" ? `{ ${Object.entries(value).map(([k, v]) => `${k}: ${valueText(v)}`).join(", ")} }` : JSON.stringify(value)
  const predicate = (query) => Object.entries(query || {}).map(([key, condition]) => Object.entries(condition && typeof condition === "object" && !Array.isArray(condition) ? condition : { "$eq": condition }).map(([operator, value]) => `${key} ${{"$eq":"==","$ne":"!=","$gt":">","$lt":"<","$gte":">=","$lte":"<=","$in":"in","$nin":"!in"}[operator] || operator} ${valueText(value)}`).join(" && ")).join(" && ")
  let head = action
  if (action === "tumi") {
    const operation = take("operation")
    if (operation === "list") {
      const resource = take("resource", "permissions" in fields ? "permissions" : "users")
      head = `read ${resource}`
      if (resource === "permissions" && "permissions" in fields && !("username" in fields)) fields.username = take("permissions")
    }
    else if (["create", "update"].includes(operation) && fields.role && typeof fields.role === "object") {
      const role = { ...take("role") }
      head = `${operation} role ${quote(role.name)}`
      delete role.name
      Object.assign(fields, role)
    } else if (["read", "delete"].includes(operation) && fields.role != null && !("username" in fields)) {
      head = `${operation} role ${quote(take("role"))}`
    } else if (["create", "delete", "update"].includes(operation)) head = `${operation} user`
    else head = operation
  } else if (action === "list") head = `read ${take("resource", "collections")}`
  else if (action === "define") {
    const resource = take("resource", "domain" in fields ? "domain" : "db")
    head = `create ${resource} ${quote("name" in fields ? take("name") : take(resource))}`
  } else if (action === "use") {
    const resource = "domain" in fields ? "domain" : "db"
    head = `use ${resource} ${quote(take(resource))}`
  } else if (["find", "read"].includes(action)) {
    head = `read collection ${quote(take("collection"))}`
    const where = take("where", null); if (where) head += ` where ${predicate(where)}`
    const projection = take("projection", null); if (projection) head += ` select [${Object.keys(projection).filter(k => projection[k]).join(", ")}]`
    const sort = take("sort", null); if (sort) head += ` order by ${Object.entries(sort).map(([k, v]) => `${k} ${Number(v) >= 0 ? "asc" : "desc"}`).join(", ")}`
    if (fields.offset != null) head += ` offset ${take("offset")}`
    if (fields.limit != null) head += ` limit ${take("limit")}`
  } else if (["insert", "create"].includes(action)) {
    const document = fields.document != null ? take("document") : take("data", {})
    head = `create in ${quote(take("collection"))} = ${valueText(document)}`
  } else if (action === "update") {
    head = `update collection ${quote(take("collection"))}`
    const where = take("where", null); if (where) head += ` where ${predicate(where)}`
    const lines = []; for (const [key, value] of Object.entries(take("set", {}))) lines.push(`${key} = ${valueText(value)};`)
    for (const [key, value] of Object.entries(take("inc", {}))) lines.push(`${key} += ${valueText(value)};`)
    for (const key of Object.keys(take("unset", {}))) lines.push(`unset ${key};`)
    head += ` { ${lines.join(" ")} }`
  } else if (action === "delete") {
    head = `delete from ${quote(take("collection"))}`
    const where = take("where", null); if (where) head += ` where ${predicate(where)}`
  } else if (["aggregate", "drop", "create_collection", "drop_collection"].includes(action)) {
    const verb = action === "create_collection" ? "create" : action === "drop_collection" ? "drop" : action
    head = `${verb} collection ${quote(take("collection"))}`
  } else if (action.startsWith("script_")) {
    const operation = action.slice(7)
    head = operation === "list" ? "read scripts" : `${operation === "execute" ? "run" : operation} script`
  } else if (action.startsWith("transaction_")) head = `${action.slice(12)} transaction`
  else if (action.startsWith("domain_")) head = `${action.slice(7)} domain ${quote("domain" in fields ? take("domain") : take("name"))}`
  else if (["drop_domain", "drop_db"].includes(action)) {
    const resource = action.slice(5)
    head = `drop ${resource} ${quote(resource in fields ? take(resource) : take("name"))}`
  } else if (action.startsWith("model_")) head = `${action === "model_get" ? "read" : "delete"} model`
  else if (["create_index", "drop_index", "list_indexes", "rebuild_indexes"].includes(action)) head = action.replace("_", " ")
  return [head, ...Object.entries(fields).filter(([, value]) => value != null).map(([key, value]) => `${key} ${quote(value)}`)].join(" ")
}
