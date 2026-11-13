/**
 * J.A.R.V.I.S. Speech-Specific Text Normalizer.
 *
 * Transforms raw text output into a natural phonemic representation optimized for Text-to-Speech synthesis.
 * Handles numbers, decimals, percentages, currency, dates, technical abbreviations, and code blocks
 * without modifying visible display text.
 */

// Number-to-word tables
const ONES = [
  '',
  'one',
  'two',
  'three',
  'four',
  'five',
  'six',
  'seven',
  'eight',
  'nine',
  'ten',
  'eleven',
  'twelve',
  'thirteen',
  'fourteen',
  'fifteen',
  'sixteen',
  'seventeen',
  'eighteen',
  'nineteen',
];

const TENS = [
  '',
  '',
  'twenty',
  'thirty',
  'forty',
  'fifty',
  'sixty',
  'seventy',
  'eighty',
  'ninety',
];

export function integerToWords(num: number): string {
  if (num === 0) return 'zero';
  if (num < 0) return `negative ${integerToWords(Math.abs(num))}`;

  if (num < 20) return ONES[num];

  if (num < 100) {
    const ten = Math.floor(num / 10);
    const rest = num % 10;
    return rest > 0 ? `${TENS[ten]}-${ONES[rest]}` : TENS[ten];
  }

  if (num < 1000) {
    const hundred = Math.floor(num / 100);
    const rest = num % 100;
    const restStr = rest > 0 ? ` ${integerToWords(rest)}` : '';
    return `${ONES[hundred]} hundred${restStr}`;
  }

  if (num < 1000000) {
    const thousand = Math.floor(num / 1000);
    const rest = num % 1000;
    const restStr = rest > 0 ? ` ${integerToWords(rest)}` : '';
    return `${integerToWords(thousand)} thousand${restStr}`;
  }

  if (num < 1000000000) {
    const million = Math.floor(num / 1000000);
    const rest = num % 1000000;
    const restStr = rest > 0 ? ` ${integerToWords(rest)}` : '';
    return `${integerToWords(million)} million${restStr}`;
  }

  return num.toString();
}

/**
 * Normalizes years between 1000 and 2099 to spoken form.
 * e.g. 1984 -> "nineteen eighty-four", 2026 -> "twenty twenty-six", 2005 -> "two thousand five"
 */
export function yearToWords(year: number): string {
  if (year >= 2000 && year <= 2009) {
    return `two thousand${year === 2000 ? '' : ` ${ONES[year - 2000]}`}`;
  }
  const century = Math.floor(year / 100);
  const decade = year % 100;
  const centuryStr = integerToWords(century);
  if (decade === 0) {
    return `${centuryStr} hundred`;
  }
  if (decade < 10) {
    return `${centuryStr} oh ${ONES[decade]}`;
  }
  return `${centuryStr} ${integerToWords(decade)}`;
}

// Extensible pronunciation dictionary for technical acronyms & specialized tokens
const PRONUNCIATION_DICTIONARY: Record<string, string> = {
  ai: 'A I',
  ml: 'M L',
  api: 'A P I',
  apis: 'A P Is',
  ui: 'U I',
  ux: 'U X',
  os: 'O S',
  cpu: 'C P U',
  cpus: 'C P Us',
  gpu: 'G P U',
  gpus: 'G P Us',
  ram: 'ram',
  rom: 'rom',
  sql: 'sequel',
  json: 'jason',
  html: 'H T M L',
  css: 'C S S',
  http: 'H T T P',
  https: 'H T T P S',
  url: 'U R L',
  urls: 'U R Ls',
  cli: 'C L I',
  sdk: 'S D K',
  sdks: 'S D Ks',
  ide: 'I D E',
  tts: 'T T S',
  stt: 'S T T',
  llm: 'L L M',
  llms: 'L L Ms',
  ocr: 'O C R',
  sse: 'S S E',
  rest: 'rest',
  gui: 'gooey',
  faq: 'F A Q',
  vcs: 'V C S',
  onnx: 'on-ix',
  regex: 'reg-ex',
  io: 'I O',
  ipc: 'I P C',
  wpm: 'words per minute',
  fps: 'frames per second',
  ms: 'milliseconds',
  kb: 'kilobytes',
  mb: 'megabytes',
  gb: 'gigabytes',
  ghz: 'gigahertz',
  mhz: 'megahertz',
};

// Common abbreviations and honorifics
const TITLE_ABBREVIATIONS: Record<string, string> = {
  dr: 'Doctor',
  mr: 'Mister',
  mrs: 'Missus',
  ms: 'Miz',
  prof: 'Professor',
  sr: 'Senior',
  jr: 'Junior',
  vs: 'versus',
  etc: 'etcetera',
  approx: 'approximately',
  dept: 'department',
  fig: 'figure',
  no: 'number',
  vol: 'volume',
  gen: 'General',
  col: 'Colonel',
  sgt: 'Sergeant',
  capt: 'Captain',
  lt: 'Lieutenant',
};

/**
 * Register a custom pronunciation in the runtime dictionary.
 */
export function registerPronunciation(term: string, spoken: string): void {
  PRONUNCIATION_DICTIONARY[term.toLowerCase()] = spoken;
}

/**
 * Look up a pronunciation from the runtime dictionary.
 */
export function lookupPronunciation(term: string): string | undefined {
  return PRONUNCIATION_DICTIONARY[term.toLowerCase()];
}

/**
 * Normalizes numbers, decimals, percentages, currency, dates, technical terms,
 * and markdown delimiters into a calm, natural phonemic representation.
 */
export function normalizeTextForSpeech(text: string): string {
  if (!text || !text.trim()) return '';

  let s = text.trim();

  // 1. Multi-line code blocks -> spoken cue
  s = s.replace(/```[\w\-]*\n[\s\S]*?```/g, ' Code snippet omitted. ');
  s = s.replace(/```[\s\S]*?```/g, ' Code snippet omitted. ');

  // 2. Inline code backticks -> raw content without backtick characters
  s = s.replace(/`([^`]+)`/g, '$1');

  // 3. Image embeds -> remove
  s = s.replace(/!\[([^\]]*)\]\([^)]+\)/g, '');

  // 4. Markdown links [title](url) -> title
  s = s.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');

  // 5. Bare URLs -> natural phrase
  s = s.replace(/https?:\/\/(?:www\.)?([a-zA-Z0-9.\-]+)\S*/gi, '$1 link');

  // 6. Markdown headers, bold, italics, blockquotes
  s = s.replace(/^#{1,6}\s+/gm, '');
  s = s.replace(/[*_]{1,3}([^*_]+)[*_]{1,3}/g, '$1');
  s = s.replace(/^>\s*/gm, '');

  // 7. Markdown list bullets & numbered items
  s = s.replace(/^\s*[-*+]\s+\[[ xX]\]\s+/gm, '');
  s = s.replace(/^\s*[-*+]\s+/gm, '');
  // Replace list items like "1. Item" -> "Item" so numbers aren't read jarringly
  s = s.replace(/^\s*\d+\.\s+/gm, '');

  // 8. Remove HTML tags & emojis
  s = s.replace(/<[^>]+>/g, '');
  s = s.replace(/[\uD800-\uDBFF][\uDC00-\uDFFF]/g, '');

  // 9. Currency normalizations
  const replaceCurrency = (rawVal: string, currencyName: string, centName = 'cents'): string => {
    if (rawVal.includes('.')) {
      const parts = rawVal.split('.');
      const whole = parts[0] ? parseInt(parts[0], 10) : 0;
      let centsPart = parts[1] || '';
      if (centsPart.length === 1) centsPart += '0';
      const cents = parseInt(centsPart.slice(0, 2), 10);
      const wholeStr = integerToWords(whole);
      const centsStr = integerToWords(cents);
      if (whole > 0 && cents > 0) {
        return `${wholeStr} ${currencyName} and ${centsStr} ${centName}`;
      } else if (cents > 0) {
        return `${centsStr} ${centName}`;
      } else {
        return `${wholeStr} ${currencyName}`;
      }
    } else {
      return `${integerToWords(parseInt(rawVal, 10))} ${currencyName}`;
    }
  };

  s = s.replace(/\bNPR\s*(\d+(?:\.\d+)?)\b/gi, (_, n) => replaceCurrency(n, 'Nepalese rupees', 'paisa'));
  s = s.replace(/\$\s*(\d+(?:\.\d+)?)\b/g, (_, n) => replaceCurrency(n, 'dollars', 'cents'));
  s = s.replace(/€\s*(\d+(?:\.\d+)?)\b/g, (_, n) => replaceCurrency(n, 'euros', 'cents'));
  s = s.replace(/£\s*(\d+(?:\.\d+)?)\b/g, (_, n) => replaceCurrency(n, 'pounds', 'pence'));
  s = s.replace(/₹\s*(\d+(?:\.\d+)?)\b/g, (_, n) => replaceCurrency(n, 'Indian rupees', 'paisa'));
  s = s.replace(/¥\s*(\d+(?:\.\d+)?)\b/g, (_, n) => `${integerToWords(Math.round(parseFloat(n)))} yen`);

  // 10. Percentages
  s = s.replace(/(\d+(?:\.\d+)?)\s*%/g, (_, n) => `${normalizeNumericExpression(n)} percent`);

  // 11. Time expressions (e.g. 10:30 AM, 3:00 PM)
  s = s.replace(/\b(\d{1,2}):(\d{2})\s*(am|pm|AM|PM)\b/g, (_, h, m, meridiem) => {
    const hour = parseInt(h, 10);
    const minute = parseInt(m, 10);
    const hourStr = integerToWords(hour);
    let minStr = '';
    if (minute === 0) {
      minStr = '';
    } else if (minute < 10) {
      minStr = ` oh ${integerToWords(minute)}`;
    } else {
      minStr = ` ${integerToWords(minute)}`;
    }
    const peri = meridiem.toUpperCase().split('').join(' ');
    return `${hourStr}${minStr} ${peri}`;
  });

  // 12. Common Latin phrases
  s = s.replace(/\be\.g\.,?\s*/gi, 'for example, ');
  s = s.replace(/\bi\.e\.,?\s*/gi, 'that is, ');
  s = s.replace(/\betc\b\.?/gi, 'etcetera');

  // 13. Titles & Honorifics (Dr., Mr., etc.)
  s = s.replace(/\b([A-Za-z]{2,5})\.\s+(?=[A-Z])/g, (match, word) => {
    const lower = word.toLowerCase();
    if (TITLE_ABBREVIATIONS[lower]) {
      return `${TITLE_ABBREVIATIONS[lower]} `;
    }
    return match;
  });

  // 14. Version tags (v2, v3, v2.5)
  s = s.replace(/\bv(\d+(?:\.\d+)?)\b/gi, 'version $1');

  // 15. Standalone Years (e.g. in 2026, year 1999)
  s = s.replace(/\b(19\d{2}|20\d{2})\b/g, (match) => {
    const y = parseInt(match, 10);
    return yearToWords(y);
  });

  // 16. Programming & Tech brand normalizations
  s = s.replace(/\bC\+\+\b/g, 'C plus plus');
  s = s.replace(/\bC#\b/g, 'C sharp');
  s = s.replace(/\.NET\b/gi, 'dot net');
  s = s.replace(/\bNode\.js\b/gi, 'Node dot J S');
  s = s.replace(/\bVue\.js\b/gi, 'Vue dot J S');
  s = s.replace(/\bReact\.js\b/gi, 'React dot J S');
  s = s.replace(/\bGitHub\b/gi, 'Git Hub');
  s = s.replace(/\bGitLab\b/gi, 'Git Lab');

  // 17. Word-level acronym / pronunciation replacements
  const words = s.split(/\b/);
  for (let i = 0; i < words.length; i++) {
    const w = words[i].toLowerCase();
    if (PRONUNCIATION_DICTIONARY[w]) {
      words[i] = PRONUNCIATION_DICTIONARY[w];
    }
  }
  s = words.join('');

  // 18. Remaining standalone decimals (e.g. 3.14 -> "three point one four")
  s = s.replace(/\b(\d+)\.(\d+)\b/g, (_, whole, frac) => {
    const wholeStr = integerToWords(parseInt(whole, 10));
    const fracDigits = frac.split('').map((d: string) => integerToWords(parseInt(d, 10))).join(' ');
    return `${wholeStr} point ${fracDigits}`;
  });

  // 19. Clean up excess symbols and spaces (preserve internal underscores in variable names)
  s = s.replace(/[#*~`><|]/g, ' ');
  s = s.replace(/(^|\s)_+|_+(\s|$)/g, '$1 $2');
  s = s.replace(/\s+/g, ' ');
  s = s.replace(/\s+([.,!?;:])/g, '$1');

  return s.trim();
}

/**
 * Helper to convert arbitrary numeric strings (integers or decimals) to words.
 */
export function normalizeNumericExpression(numStr: string): string {
  if (numStr.includes('.')) {
    const parts = numStr.split('.');
    const whole = integerToWords(parseInt(parts[0], 10) || 0);
    const frac = parts[1].split('').map((d) => integerToWords(parseInt(d, 10))).join(' ');
    return `${whole} point ${frac}`;
  }
  const val = parseInt(numStr, 10);
  return isNaN(val) ? numStr : integerToWords(val);
}
