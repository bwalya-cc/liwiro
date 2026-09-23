type JsonLikeValue =
  | null
  | boolean
  | number
  | string
  | JsonLikeValue[]
  | { [key: string]: JsonLikeValue }

function isPlainObject(value: unknown): value is Record<string, JsonLikeValue> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

function isIdentifierStart(char: string) {
  return /[A-Za-z_$]/.test(char)
}

function isIdentifierPart(char: string) {
  return /[A-Za-z0-9_$]/.test(char)
}

class JsonLikeParser {
  private index = 0

  constructor(private readonly text: string) {}

  parse(): JsonLikeValue {
    this.skipIgnorable()
    const value = this.parseValue()
    this.skipIgnorable()
    if (!this.isAtEnd()) {
      this.error("Unexpected trailing content")
    }
    return value
  }

  private isAtEnd() {
    return this.index >= this.text.length
  }

  private peek(offset = 0) {
    return this.text[this.index + offset] || ""
  }

  private advance() {
    const char = this.text[this.index] || ""
    this.index += 1
    return char
  }

  private error(message: string): never {
    throw new Error(`${message} at position ${this.index + 1}`)
  }

  private skipIgnorable() {
    while (!this.isAtEnd()) {
      const char = this.peek()
      if (/\s/.test(char)) {
        this.index += 1
        continue
      }
      if (char === "/" && this.peek(1) === "/") {
        this.index += 2
        while (!this.isAtEnd()) {
          const next = this.advance()
          if (next === "\n" || next === "\r") break
        }
        continue
      }
      if (char === "/" && this.peek(1) === "*") {
        const endIndex = this.text.indexOf("*/", this.index + 2)
        if (endIndex === -1) {
          this.error("Unterminated block comment")
        }
        this.index = endIndex + 2
        continue
      }
      break
    }
  }

  private expect(char: string) {
    this.skipIgnorable()
    if (this.peek() !== char) {
      this.error(`Expected '${char}'`)
    }
    this.index += 1
  }

  private parseValue(): JsonLikeValue {
    this.skipIgnorable()
    const char = this.peek()
    if (!char) {
      this.error("Unexpected end of input")
    }

    if (char === "{") return this.parseObject()
    if (char === "[") return this.parseArray()
    if (char === '"' || char === "'") return this.parseString()
    if (char === "-" || /\d/.test(char)) return this.parseNumber()

    if (this.text.startsWith("true", this.index) && !isIdentifierPart(this.peek(4))) {
      this.index += 4
      return true
    }
    if (this.text.startsWith("false", this.index) && !isIdentifierPart(this.peek(5))) {
      this.index += 5
      return false
    }
    if (this.text.startsWith("null", this.index) && !isIdentifierPart(this.peek(4))) {
      this.index += 4
      return null
    }

    this.error(`Unexpected token '${char}'`)
  }

  private parseObject(): Record<string, JsonLikeValue> {
    const out: Record<string, JsonLikeValue> = {}
    this.expect("{")
    this.skipIgnorable()
    if (this.peek() === "}") {
      this.index += 1
      return out
    }

    while (true) {
      this.skipIgnorable()
      const char = this.peek()
      const key =
        char === '"' || char === "'"
          ? this.parseString()
          : this.parseIdentifier("object key")

      this.expect(":")
      out[key] = this.parseValue()

      this.skipIgnorable()
      if (this.peek() === ",") {
        this.index += 1
        this.skipIgnorable()
        if (this.peek() === "}") {
          this.index += 1
          break
        }
        continue
      }
      if (this.peek() === "}") {
        this.index += 1
        break
      }
      this.error("Expected ',' or '}'")
    }

    return out
  }

  private parseArray(): JsonLikeValue[] {
    const out: JsonLikeValue[] = []
    this.expect("[")
    this.skipIgnorable()
    if (this.peek() === "]") {
      this.index += 1
      return out
    }

    while (true) {
      out.push(this.parseValue())
      this.skipIgnorable()
      if (this.peek() === ",") {
        this.index += 1
        this.skipIgnorable()
        if (this.peek() === "]") {
          this.index += 1
          break
        }
        continue
      }
      if (this.peek() === "]") {
        this.index += 1
        break
      }
      this.error("Expected ',' or ']'")
    }

    return out
  }

  private parseString() {
    const quote = this.advance()
    let out = ""

    while (!this.isAtEnd()) {
      const char = this.advance()
      if (char === quote) {
        return out
      }
      if (char === "\n" || char === "\r") {
        this.error("Unterminated string")
      }
      if (char !== "\\") {
        out += char
        continue
      }

      if (this.isAtEnd()) {
        this.error("Unterminated escape sequence")
      }
      const escaped = this.advance()
      if (escaped === "u") {
        const hex = this.text.slice(this.index, this.index + 4)
        if (!/^[0-9a-fA-F]{4}$/.test(hex)) {
          this.error("Invalid unicode escape")
        }
        out += String.fromCharCode(Number.parseInt(hex, 16))
        this.index += 4
        continue
      }

      const map: Record<string, string> = {
        '"': '"',
        "'": "'",
        "\\": "\\",
        "/": "/",
        b: "\b",
        f: "\f",
        n: "\n",
        r: "\r",
        t: "\t",
      }
      if (!(escaped in map)) {
        this.error(`Invalid escape '\\${escaped}'`)
      }
      out += map[escaped]
    }

    this.error("Unterminated string")
  }

  private parseIdentifier(context: string) {
    const start = this.peek()
    if (!isIdentifierStart(start)) {
      this.error(`Expected ${context}`)
    }

    let value = start
    this.index += 1
    while (!this.isAtEnd() && isIdentifierPart(this.peek())) {
      value += this.advance()
    }
    return value
  }

  private parseNumber() {
    const remaining = this.text.slice(this.index)
    const match = remaining.match(/^-?(0|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?/)
    if (!match) {
      this.error("Invalid number")
    }

    const token = match[0]
    this.index += token.length
    const value = Number(token)
    if (!Number.isFinite(value)) {
      this.error("Invalid number")
    }
    return value
  }
}

export function parseJsonLikeText(value: string): JsonLikeValue {
  const text = String(value || "").trim()
  if (!text) {
    throw new Error("Input is empty")
  }
  try {
    return JSON.parse(text)
  } catch {
    return new JsonLikeParser(text).parse()
  }
}

export function parseJsonLikeObject(value: string, label = "JSON") {
  const parsed = parseJsonLikeText(value)
  if (!isPlainObject(parsed)) {
    throw new Error(`${label} must be a JSON object`)
  }
  return parsed
}

export function validateJsonText(value: string) {
  const text = String(value || "").trim()
  if (!text) {
    return { valid: true, message: "", formatted: "" }
  }
  try {
    const parsed = parseJsonLikeText(text)
    return {
      valid: true,
      message: "",
      formatted: JSON.stringify(parsed, null, 2),
    }
  } catch (error) {
    return {
      valid: false,
      message: error instanceof Error ? error.message : "Invalid JSON",
      formatted: "",
    }
  }
}
