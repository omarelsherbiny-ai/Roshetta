// web/src/lib/theme.ts (theme store for client components: read, apply, save, and the useTheme hook)
import { useCallback, useEffect, useState } from "react";
import {
  DEFAULT_THEME,
  THEME_COLORS,
  THEME_STORAGE_KEY,
  type ThemeChoice,
} from "./themeScript";

export type { ThemeChoice } from "./themeScript";
export { DEFAULT_THEME, THEME_STORAGE_KEY } from "./themeScript";

/** The three choices, in the order the Settings picker shows them. */
export const THEME_CHOICES: readonly ThemeChoice[] = ["light", "dark", "system"];

export type ResolvedTheme = "light" | "dark";

const listeners = new Set<() => void>();

export function isThemeChoice(value: unknown): value is ThemeChoice {
  return value === "light" || value === "dark" || value === "system";
}

/** Saved choice, or DEFAULT_THEME when nothing valid is saved or storage is blocked. */
export function readTheme(): ThemeChoice {
  try {
    const saved = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isThemeChoice(saved) ? saved : DEFAULT_THEME;
  } catch {
    return DEFAULT_THEME;
  }
}

export function systemPrefersDark(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export function resolveTheme(choice: ThemeChoice): ResolvedTheme {
  if (choice === "system") return systemPrefersDark() ? "dark" : "light";
  return choice;
}

/** Puts the resolved theme on <html> (same effect as the pre-paint script). Does not save. */
export function applyTheme(choice: ThemeChoice): ResolvedTheme {
  const resolved = resolveTheme(choice);
  const root = document.documentElement;
  root.classList.toggle("dark", resolved === "dark");
  root.style.colorScheme = resolved;
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute("content", THEME_COLORS[resolved]);
  return resolved;
}

/** Saves the choice on this device, applies it, and tells every mounted useTheme(). */
export function setTheme(choice: ThemeChoice): void {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, choice);
  } catch {
    /* storage blocked: the choice still applies until the page closes */
  }
  applyTheme(choice);
  listeners.forEach((notify) => notify());
}

/**
 * Hook for the Settings picker (and anything that needs to know the theme).
 * First render returns DEFAULT_THEME so server and client markup match; the saved choice is read right after mount.
 */
export function useTheme(): {
  theme: ThemeChoice;
  resolved: ResolvedTheme;
  setTheme: (choice: ThemeChoice) => void;
} {
  const [theme, setThemeState] = useState<ThemeChoice>(DEFAULT_THEME);
  const [resolved, setResolved] = useState<ResolvedTheme>("light");

  useEffect(() => {
    const sync = () => {
      const choice = readTheme();
      setThemeState(choice);
      setResolved(resolveTheme(choice));
    };
    sync();
    listeners.add(sync);

    // Follow the device while the choice is "system", and follow changes made in another tab.
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onMedia = () => {
      if (readTheme() === "system") {
        applyTheme("system");
        sync();
      }
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === THEME_STORAGE_KEY) {
        applyTheme(readTheme());
        sync();
      }
    };
    media.addEventListener("change", onMedia);
    window.addEventListener("storage", onStorage);
    return () => {
      listeners.delete(sync);
      media.removeEventListener("change", onMedia);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  const choose = useCallback((choice: ThemeChoice) => setTheme(choice), []);
  return { theme, resolved, setTheme: choose };
}