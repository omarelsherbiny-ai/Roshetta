// web/src/lib/themeScript.ts (theme constants and the pre-paint script; no React, safe to import from server components)

export type ThemeChoice = "light" | "dark" | "system";

/** Where the choice is stored: this device only (localStorage). */
export const THEME_STORAGE_KEY = "roshetta_theme";

/**
 * Used when nothing is saved yet. "light" on purpose: switch to "system" only after every page has been
 * checked in dark (pages that still hold fixed colors would look broken for people whose device is dark).
 */
export const DEFAULT_THEME: ThemeChoice = "light";

/** Browser-bar color per resolved theme (equals the `surface` token of each set). */
export const THEME_COLORS = { light: "#ecfef3", dark: "#0d1512" } as const;

/**
 * Runs inline in <head> before first paint: reads the saved choice, resolves "system" with
 * prefers-color-scheme, and sets the `dark` class, `color-scheme` and the theme-color meta on <html>.
 * Wrapped in try/catch so a blocked localStorage never breaks the page.
 */
export const THEME_INIT_SCRIPT = `(function(){try{
var c=localStorage.getItem(${JSON.stringify(THEME_STORAGE_KEY)});
if(c!=='light'&&c!=='dark'&&c!=='system')c=${JSON.stringify(DEFAULT_THEME)};
var d=c==='dark'||(c==='system'&&window.matchMedia('(prefers-color-scheme: dark)').matches);
var r=document.documentElement;
if(d)r.classList.add('dark');else r.classList.remove('dark');
r.style.colorScheme=d?'dark':'light';
var m=document.querySelector('meta[name="theme-color"]');
if(m)m.setAttribute('content',d?${JSON.stringify(THEME_COLORS.dark)}:${JSON.stringify(THEME_COLORS.light)});
}catch(e){}})();`;