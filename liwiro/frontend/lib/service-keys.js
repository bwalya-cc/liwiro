"use client"

const KEY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"

function randomIndex(limit) {
  if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    const buffer = new Uint32Array(1)
    crypto.getRandomValues(buffer)
    return buffer[0] % limit
  }
  return Math.floor(Math.random() * limit)
}

export function generateLiwiroKey(prefix = "liwiro_", length = 24) {
  const size = Math.max(12, Number(length) || 24)
  let suffix = ""
  for (let index = 0; index < size; index += 1) {
    suffix += KEY_ALPHABET[randomIndex(KEY_ALPHABET.length)]
  }
  return `${String(prefix || "")}${suffix}`
}
