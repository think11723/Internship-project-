/**
 * HTML entity decoding for backend-supplied text.
 *
 * Company records are assembled from scraped press releases, RSS feeds and
 * careers pages, so their text arrives HTML-encoded: `Anthropic&rsquo;s`,
 * `Series&nbsp;B`, `R&amp;D`. React renders `{expr}` as a literal text node
 * and never decodes entities, so without this the raw `&rsquo;` reaches the
 * user.
 *
 * SINGLE APPLICATION POINT
 * ------------------------
 * `decodeDeep` is applied exactly once, in the axios response interceptor in
 * `services/api.js`. Every service module imports that shared instance, so
 * all backend data is decoded before it reaches a component. Do NOT call
 * these helpers again inside components or services — a second pass would
 * decode content that was legitimately double-encoded (`&amp;lt;` is meant to
 * display as `&lt;`, not as `<`).
 *
 * SAFETY
 * ------
 * Decoding is not an XSS vector here: no call site uses
 * `dangerouslySetInnerHTML`, so React escapes every one of these strings again
 * on render. The output is data, never markup.
 */

/**
 * Named entities that actually occur in scraped company/news copy.
 *
 * Deliberately curated rather than exhaustive — the full HTML5 set is ~2,200
 * entries and everything outside this list is far more likely to be literal
 * text than a real entity.
 */
const NAMED_ENTITIES = {
  // Quotes and apostrophes — by far the most common offenders.
  ldquo: '“', // "
  rdquo: '”', // "
  lsquo: '‘', // '
  rsquo: '’', // '
  quot: '"',
  apos: "'",
  sbquo: '‚',
  bdquo: '„',
  laquo: '«',
  raquo: '»',

  // Structural — `amp` must be present for `R&amp;D`.
  amp: '&',
  lt: '<',
  gt: '>',
  nbsp: ' ',

  // Dashes, ellipses and spacing.
  ndash: '–',
  mdash: '—',
  hellip: '…',
  bull: '•',
  middot: '·',
  ensp: ' ',
  emsp: ' ',
  thinsp: ' ',
  shy: '­',

  // Symbols common in funding / legal copy.
  trade: '™',
  copy: '©',
  reg: '®',
  deg: '°',
  euro: '€',
  pound: '£',
  yen: '¥',
  cent: '¢',
  permil: '‰',
  plusmn: '±',
  times: '×',
  divide: '÷',
  frac12: '½',
  frac14: '¼',
  frac34: '¾',
  sup2: '²',
  sup3: '³',
  micro: 'µ',
  dagger: '†',
  Dagger: '‡',
  larr: '←',
  rarr: '→',
  harr: '↔',

  // Accented letters seen in founder and city names.
  eacute: 'é',
  Eacute: 'É',
  egrave: 'è',
  agrave: 'à',
  aacute: 'á',
  iacute: 'í',
  oacute: 'ó',
  uacute: 'ú',
  ntilde: 'ñ',
  ccedil: 'ç',
  uuml: 'ü',
  ouml: 'ö',
  auml: 'ä',
  szlig: 'ß',
  oslash: 'ø',
  aring: 'å',
  aelig: 'æ',
}

/**
 * Matches a named (`&amp;`), decimal (`&#39;`) or hex (`&#x27;`) entity.
 *
 * The trailing semicolon is REQUIRED. HTML permits a few legacy entities
 * without one, but honouring that would rewrite ordinary prose — `AT&T`,
 * `R&D` and `Q&A` all begin with what looks like `&amp`/`&notin`. Requiring
 * the semicolon keeps those literal.
 */
const ENTITY_PATTERN = /&(#\d{1,7}|#[xX][0-9a-fA-F]{1,6}|[a-zA-Z][a-zA-Z0-9]{1,31});/g

/** Highest valid Unicode code point. */
const MAX_CODE_POINT = 0x10ffff

/**
 * Windows-1252 replacements for the C1 range.
 *
 * Scrapers routinely emit `&#146;` for a right single quote because the
 * source page was mislabelled as UTF-8 when it was really Windows-1252.
 * Decoding those literally yields invisible control characters, so map them
 * the way every browser does.
 */
const CP1252_OVERRIDES = {
  128: '€', 130: '‚', 131: 'ƒ', 132: '„', 133: '…',
  134: '†', 135: '‡', 136: 'ˆ', 137: '‰', 138: 'Š',
  139: '‹', 140: 'Œ', 142: 'Ž', 145: '‘', 146: '’',
  147: '“', 148: '”', 149: '•', 150: '–', 151: '—',
  152: '˜', 153: '™', 154: 'š', 155: '›', 156: 'œ',
  158: 'ž', 159: 'Ÿ',
}

/**
 * Convert a numeric character reference to its character.
 * Returns null when the code point is unusable, so the caller can leave the
 * original text untouched rather than emitting a replacement character.
 */
function decodeNumericEntity(body) {
  const isHex = body[1] === 'x' || body[1] === 'X'
  const code = parseInt(isHex ? body.slice(2) : body.slice(1), isHex ? 16 : 10)

  if (!Number.isFinite(code) || code <= 0 || code > MAX_CODE_POINT) return null
  if (Object.prototype.hasOwnProperty.call(CP1252_OVERRIDES, code)) {
    return CP1252_OVERRIDES[code]
  }
  // Lone surrogates are not representable on their own.
  if (code >= 0xd800 && code <= 0xdfff) return null

  try {
    return String.fromCodePoint(code)
  } catch {
    return null
  }
}

/**
 * Decode HTML entities in a single string.
 *
 * Runs as ONE pass: `String.replace` never rescans its own output, so
 * `&amp;rsquo;` decodes to the literal text `&rsquo;` rather than to `'`.
 * That is intentional — see the "do not decode twice" note above.
 *
 * Unrecognised entities are returned verbatim.
 *
 * @param {string} value
 * @returns {string}
 */
export function decodeHtmlEntities(value) {
  if (typeof value !== 'string' || value.length === 0) return value
  // Cheap bail-out: the overwhelming majority of strings contain no '&'.
  if (value.indexOf('&') === -1) return value

  return value.replace(ENTITY_PATTERN, (match, body) => {
    if (body[0] === '#') {
      const decoded = decodeNumericEntity(body)
      return decoded === null ? match : decoded
    }
    return Object.prototype.hasOwnProperty.call(NAMED_ENTITIES, body)
      ? NAMED_ENTITIES[body]
      : match
  })
}

/** Keys that must never be written when rebuilding an object. */
const UNSAFE_KEYS = new Set(['__proto__', 'constructor', 'prototype'])

/**
 * True for objects we own and may safely rebuild — plain objects and arrays
 * only. Blobs, FormData, Files, Dates, Maps and class instances are returned
 * untouched so binary downloads and uploads pass through intact.
 */
function isPlainContainer(value) {
  if (Array.isArray(value)) return true
  if (value === null || typeof value !== 'object') return false
  const proto = Object.getPrototypeOf(value)
  return proto === Object.prototype || proto === null
}

/**
 * Recursively decode every string in a JSON-shaped value.
 *
 * Structure, key order and non-string values are preserved. Company payloads
 * nest several levels deep (`recommendation.intelligence.reasoning[]`,
 * `recommendation.opportunity_v2.opportunity_strengths[]`), so a shallow pass
 * would miss most of the user-visible copy.
 *
 * @param {*} value
 * @returns {*} the decoded value
 */
export function decodeDeep(value) {
  return decodeDeepInternal(value, new WeakSet())
}

function decodeDeepInternal(value, seen) {
  if (typeof value === 'string') return decodeHtmlEntities(value)
  if (!isPlainContainer(value)) return value

  // Defensive: JSON responses are acyclic, but a cycle would hang the tab.
  if (seen.has(value)) return value
  seen.add(value)

  if (Array.isArray(value)) {
    return value.map((item) => decodeDeepInternal(item, seen))
  }

  const out = {}
  for (const key of Object.keys(value)) {
    if (UNSAFE_KEYS.has(key)) continue
    out[key] = decodeDeepInternal(value[key], seen)
  }
  return out
}
