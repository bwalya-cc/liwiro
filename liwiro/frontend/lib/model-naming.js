const IRREGULAR_PLURALS = {
  analysis: "analyses",
  axis: "axes",
  basis: "bases",
  child: "children",
  crisis: "crises",
  criterion: "criteria",
  datum: "data",
  diagnosis: "diagnoses",
  foot: "feet",
  goose: "geese",
  index: "indices",
  man: "men",
  matrix: "matrices",
  medium: "media",
  mouse: "mice",
  ox: "oxen",
  parenthesis: "parentheses",
  person: "people",
  phenomenon: "phenomena",
  quiz: "quizzes",
  synopsis: "synopses",
  thesis: "theses",
  tooth: "teeth",
  vertex: "vertices",
  woman: "women",
}

const REVERSE_IRREGULAR_PLURALS = Object.fromEntries(
  Object.entries(IRREGULAR_PLURALS).map(([singular, plural]) => [plural, singular]),
)

const UNCOUNTABLE_WORDS = new Set([
  "aircraft",
  "deer",
  "equipment",
  "fish",
  "information",
  "metadata",
  "money",
  "moose",
  "rice",
  "series",
  "sheep",
  "species",
])

const F_TO_V_EXCEPTIONS = new Set([
  "belief",
  "chief",
  "cliff",
  "proof",
  "reef",
  "roof",
  "safe",
])

const O_ES_WORDS = new Set([
  "echo",
  "hero",
  "potato",
  "tomato",
  "torpedo",
  "veto",
])

function pluralizeSingularWord(word) {
  const text = String(word || "").trim().toLowerCase()
  if (!text) return ""
  if (UNCOUNTABLE_WORDS.has(text)) return text
  if (IRREGULAR_PLURALS[text]) return IRREGULAR_PLURALS[text]
  if (/[^aeiou]y$/.test(text)) {
    return `${text.slice(0, -1)}ies`
  }
  if (O_ES_WORDS.has(text)) {
    return `${text}es`
  }
  if (/(s|x|ch|sh|zz)$/.test(text)) {
    return `${text}es`
  }
  if (/fe$/.test(text) && !F_TO_V_EXCEPTIONS.has(text)) {
    return `${text.slice(0, -2)}ves`
  }
  if (/f$/.test(text) && !F_TO_V_EXCEPTIONS.has(text)) {
    return `${text.slice(0, -1)}ves`
  }
  return `${text}s`
}

function singularizePluralCandidate(word) {
  const text = String(word || "").trim().toLowerCase()
  if (!text) return ""
  if (UNCOUNTABLE_WORDS.has(text)) return text
  if (REVERSE_IRREGULAR_PLURALS[text]) return REVERSE_IRREGULAR_PLURALS[text]
  if (/[^aeiou]ies$/.test(text)) {
    return `${text.slice(0, -3)}y`
  }
  if (/ves$/.test(text)) {
    const asFe = `${text.slice(0, -3)}fe`
    if (pluralizeSingularWord(asFe) === text) return asFe
    const asF = `${text.slice(0, -3)}f`
    if (pluralizeSingularWord(asF) === text) return asF
  }
  if (/oes$/.test(text)) {
    const singular = text.slice(0, -2)
    if (pluralizeSingularWord(singular) === text) return singular
  }
  if (/(ches|shes|sses|xes|zzes)$/.test(text)) {
    const singular = text.slice(0, -2)
    if (pluralizeSingularWord(singular) === text) return singular
  }
  if (/s$/.test(text) && !/(ss|us|is)$/.test(text)) {
    const singular = text.slice(0, -1)
    if (pluralizeSingularWord(singular) === text) return singular
  }
  return text
}

function pluralizeWord(word) {
  const text = String(word || "").trim().toLowerCase()
  if (!text) return ""
  if (UNCOUNTABLE_WORDS.has(text)) return text
  if (REVERSE_IRREGULAR_PLURALS[text]) return text

  const singularCandidate = singularizePluralCandidate(text)
  if (singularCandidate !== text && pluralizeSingularWord(singularCandidate) === text) {
    return text
  }

  return pluralizeSingularWord(text)
}

export function generateCollectionNameFromModelName(modelName) {
  const raw = String(modelName || "").trim()
  if (!raw) return ""

  const normalized = raw
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/([A-Z]+)([A-Z][a-z])/g, "$1 $2")
    .replace(/[^A-Za-z0-9]+/g, " ")
    .trim()

  if (!normalized) return ""

  const parts = normalized
    .split(/\s+/)
    .map((part) => String(part || "").trim().toLowerCase())
    .filter(Boolean)

  if (parts.length === 0) return ""

  const lastIndex = parts.length - 1
  parts[lastIndex] = pluralizeWord(parts[lastIndex])
  return parts.join("_")
}
