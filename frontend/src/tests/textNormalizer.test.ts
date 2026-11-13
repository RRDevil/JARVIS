import { describe, it, expect } from 'vitest';
import {
  normalizeTextForSpeech,
  integerToWords,
  yearToWords,
  registerPronunciation,
  lookupPronunciation,
} from '../services/textNormalizer';

describe('TextNormalizer (Frontend Speech Processor)', () => {
  it('converts integers to words correctly', () => {
    expect(integerToWords(0)).toBe('zero');
    expect(integerToWords(7)).toBe('seven');
    expect(integerToWords(19)).toBe('nineteen');
    expect(integerToWords(25)).toBe('twenty-five');
    expect(integerToWords(500)).toBe('five hundred');
    expect(integerToWords(2026)).toBe('two thousand twenty-six');
  });

  it('converts years to words contextually', () => {
    expect(yearToWords(2026)).toBe('twenty twenty-six');
    expect(yearToWords(1995)).toBe('nineteen ninety-five');
    expect(yearToWords(2000)).toBe('two thousand');
    expect(yearToWords(2008)).toBe('two thousand eight');

    const res = normalizeTextForSpeech('Founded in 2026.');
    expect(res).toContain('twenty twenty-six');
  });

  it('normalizes currency expressions with dollars and cents', () => {
    // NPR
    const resNpr = normalizeTextForSpeech('Total bill is NPR 500.');
    expect(resNpr).toContain('five hundred Nepalese rupees');

    // USD with cents
    const resUsd = normalizeTextForSpeech('The subscription is $3.50.');
    expect(resUsd).toContain('three dollars and fifty cents');

    // Simple USD
    const resUsdWhole = normalizeTextForSpeech('Costs $25.');
    expect(resUsdWhole).toContain('twenty-five dollars');
  });

  it('normalizes percentage expressions', () => {
    const res = normalizeTextForSpeech('Battery level is 25%.');
    expect(res).toContain('twenty-five percent');

    const resDec = normalizeTextForSpeech('CPU load is 3.14%.');
    expect(resDec).toContain('three point one four percent');
  });

  it('normalizes time expressions', () => {
    const res = normalizeTextForSpeech('Meeting is at 10:30 AM.');
    expect(res).toContain('ten thirty A M');

    const resPm = normalizeTextForSpeech('Alarm set for 4:00 PM.');
    expect(resPm).toContain('four P M');
  });

  it('normalizes abbreviations and honorifics', () => {
    const res = normalizeTextForSpeech('Dr. Smith arrived at the lab, e.g. on time etc.');
    expect(res).toContain('Doctor Smith');
    expect(res).toContain('for example');
    expect(res).toContain('etcetera');
  });

  it('pronounces technical acronyms naturally', () => {
    const res = normalizeTextForSpeech('Query the SQL database and parse the JSON API response.');
    expect(res).toContain('sequel');
    expect(res).toContain('jason');
    expect(res).toContain('A P I');
  });

  it('strips markdown syntax, code fences, and links without losing content', () => {
    const md = `
# System Status
Here is a sample:
\`\`\`typescript
const a = 1;
\`\`\`
Check [documentation](https://jarvis.ai) for **critical** details.
`;
    const res = normalizeTextForSpeech(md);
    expect(res).not.toContain('#');
    expect(res).not.toContain('```');
    expect(res).not.toContain('https://');
    expect(res).not.toContain('**');
    expect(res).toContain('System Status');
    expect(res).toContain('Code snippet omitted');
    expect(res).toContain('critical details');
  });

  it('allows dynamic registration of custom pronunciations', () => {
    registerPronunciation('GraphQL', 'graph Q L');
    expect(lookupPronunciation('graphql')).toBe('graph Q L');

    const res = normalizeTextForSpeech('Serving GraphQL endpoints.');
    expect(res).toContain('graph Q L');
  });

  it('normalizes comma-separated numbers and standalone integers', () => {
    const res = normalizeTextForSpeech('Processed 1,250 requests across 42 servers.');
    expect(res).toContain('one thousand two hundred fifty requests');
    expect(res).toContain('forty-two servers');
  });

  it('normalizes negative numbers and metrics', () => {
    const res = normalizeTextForSpeech('Temperature dropped to -5 degrees with 0.21s latency and 100MB RAM.');
    expect(res).toContain('negative five degrees');
    expect(res).toContain('zero point two one seconds');
    expect(res).toContain('one hundred megabytes');
  });

  it('normalizes programming languages C++ and C# and email addresses', () => {
    const res = normalizeTextForSpeech('Write code in C++ or C# and email team@jarvis.ai.');
    expect(res).toContain('C plus plus');
    expect(res).toContain('C sharp');
    expect(res).toContain('team at jarvis dot A I');
  });

  it('guarantees identical parity for expanded corpus (dates, durations, 24h times, IPs, versions, Rs, negative pct)', () => {
    // ISO Calendar Dates
    const resDate = normalizeTextForSpeech('Release date is 2026-11-13.');
    expect(resDate).toContain('November thirteenth, twenty twenty-six');

    // Durations
    const resDur = normalizeTextForSpeech('Execution lasted 2h 30m.');
    expect(resDur).toContain('two hours thirty minutes');

    // 24-hour time format
    const res24 = normalizeTextForSpeech('Meeting at 14:30 sharp.');
    expect(res24).toContain('two thirty P M');

    // IPv4 addresses
    const resIp = normalizeTextForSpeech('Connected to 192.168.1.1 successfully.');
    expect(resIp).toContain('one hundred ninety-two dot one hundred sixty-eight dot one dot one');

    // Semantic versions
    const resVer = normalizeTextForSpeech('Upgraded to v1.2.3 today.');
    expect(resVer).toContain('version one point two point three');

    // Rs currency
    const resRs = normalizeTextForSpeech('Invoice total is Rs. 500.');
    expect(resRs).toContain('five hundred rupees');

    // Negative percentages
    const resNegPct = normalizeTextForSpeech('Variance is -3.5% overall.');
    expect(resNegPct).toContain('negative three point five percent');
  });
});

