/**
 * WCAG 2.1 AA text-contrast guard for the amber surfaces called out in #1054:
 * the Generate button (the app's single primary CTA) and the FavoritesPanel
 * cap-reached warnings.
 *
 * These assertions compute the *actual* rendered colors rather than eyeballing
 * a shade. Tailwind v4 defines the palette in OKLCH (see node_modules/
 * tailwindcss/theme.css), so we convert OKLCH → linear sRGB → luminance, and —
 * critically for the disabled states — composite `opacity` the way a browser
 * does: in gamma-encoded sRGB, over the surface behind the element. That last
 * step is why `opacity-70` failed for *every* amber shade: dimming blends both
 * the white label and the amber fill toward the page background, collapsing the
 * ratio. The fix darkens the disabled fill to amber-900 and dims only to
 * opacity-90, which we verify holds ≥4.5:1 in the light-mode worst case (dark
 * mode only pushes the blend darker, raising contrast against white text).
 */
import { describe, it, expect } from "vitest";

const AA_NORMAL = 4.5;

// --- OKLCH → linear sRGB (Björn Ottosson) ------------------------------------
function oklchToLinearSrgb(L: number, C: number, hDeg: number): [number, number, number] {
  const h = (hDeg * Math.PI) / 180;
  const a = C * Math.cos(h);
  const b = C * Math.sin(h);

  const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = L - 0.0894841775 * a - 1.291485548 * b;

  const l = l_ ** 3;
  const m = m_ ** 3;
  const s = s_ ** 3;

  const r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s;
  const g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s;
  const bl = -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s;

  return [clamp01(r), clamp01(g), clamp01(bl)];
}

// --- HSL → linear sRGB (used for the theme surfaces from index.css) ----------
function hslToLinearSrgb(hDeg: number, sPct: number, lPct: number): [number, number, number] {
  const s = sPct / 100;
  const l = lPct / 100;
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const hp = hDeg / 60;
  const x = c * (1 - Math.abs((hp % 2) - 1));
  let r = 0;
  let g = 0;
  let b = 0;
  if (hp < 1) [r, g, b] = [c, x, 0];
  else if (hp < 2) [r, g, b] = [x, c, 0];
  else if (hp < 3) [r, g, b] = [0, c, x];
  else if (hp < 4) [r, g, b] = [0, x, c];
  else if (hp < 5) [r, g, b] = [x, 0, c];
  else [r, g, b] = [c, 0, x];
  const m = l - c / 2;
  return [srgbToLinear(r + m), srgbToLinear(g + m), srgbToLinear(b + m)];
}

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
const linearToSrgb = (c: number) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);
const srgbToLinear = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);

function relativeLuminance([r, g, b]: [number, number, number]): number {
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(fg: [number, number, number], bg: [number, number, number]): number {
  const l1 = relativeLuminance(fg);
  const l2 = relativeLuminance(bg);
  const [hi, lo] = l1 >= l2 ? [l1, l2] : [l2, l1];
  return (hi + 0.05) / (lo + 0.05);
}

/**
 * Composite a foreground linear-sRGB color at `alpha` over a linear-sRGB
 * background, mimicking CSS `opacity`: browsers blend in gamma-encoded sRGB,
 * so we round-trip through the encoded space before returning to linear.
 */
function compositeOver(
  fg: [number, number, number],
  bg: [number, number, number],
  alpha: number,
): [number, number, number] {
  const mix = (f: number, b: number) => srgbToLinear(alpha * linearToSrgb(f) + (1 - alpha) * linearToSrgb(b));
  return [mix(fg[0], bg[0]), mix(fg[1], bg[1]), mix(fg[2], bg[2])];
}

// --- Palette (Tailwind v4 theme.css) + theme surfaces (index.css) ------------
const WHITE: [number, number, number] = [1, 1, 1];
const amber500 = oklchToLinearSrgb(0.769, 0.188, 70.08);
const amber700 = oklchToLinearSrgb(0.555, 0.163, 48.998);
const amber800 = oklchToLinearSrgb(0.473, 0.137, 46.201);
const amber900 = oklchToLinearSrgb(0.414, 0.112, 45.904);

// Lightest surfaces per theme — the worst case for white-text contrast under
// an opacity blend (a lighter backdrop lifts the dimmed fill toward the label).
const LIGHT_SURFACE = WHITE; // --background / --card: 0 0% 100%
const DARK_CARD = hslToLinearSrgb(220, 18, 12); // --card (dark) — lighter than --background 8%
const DISABLED_ALPHA = 0.9; // opacity-90

describe("Generate button contrast (WCAG AA, #1054)", () => {
  it("enabled: white on amber-700 clears 4.5:1", () => {
    expect(contrast(WHITE, amber700)).toBeGreaterThanOrEqual(AA_NORMAL);
  });

  it("hover: white on amber-800 clears 4.5:1", () => {
    expect(contrast(WHITE, amber800)).toBeGreaterThanOrEqual(AA_NORMAL);
  });

  // aria-disabled (precondition) and native disabled (pending) share the same
  // amber-900 @ opacity-90 treatment — verify both modes at the worst-case
  // (lightest) surface behind the button.
  for (const [mode, surface] of [
    ["light", LIGHT_SURFACE],
    ["dark", DARK_CARD],
  ] as const) {
    it(`disabled (amber-900 @ opacity-90) clears 4.5:1 in ${mode} mode`, () => {
      const label = compositeOver(WHITE, surface, DISABLED_ALPHA);
      const fill = compositeOver(amber900, surface, DISABLED_ALPHA);
      expect(contrast(label, fill)).toBeGreaterThanOrEqual(AA_NORMAL);
    });
  }

  // Guard against a regression back to the failing shade the issue reported.
  it("the old amber-500 fill would have failed (sanity check on the method)", () => {
    expect(contrast(WHITE, amber500)).toBeLessThan(AA_NORMAL);
  });
});

describe("FavoritesPanel cap-warning contrast (WCAG AA, #1054)", () => {
  it("light mode: text-amber-800 on the white card clears 4.5:1", () => {
    expect(contrast(amber800, LIGHT_SURFACE)).toBeGreaterThanOrEqual(AA_NORMAL);
  });

  it("dark mode: text-amber-500 on the dark card clears 4.5:1", () => {
    expect(contrast(amber500, DARK_CARD)).toBeGreaterThanOrEqual(AA_NORMAL);
  });
});
