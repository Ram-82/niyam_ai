"use client";

import { createContext, useContext, useEffect, useState } from "react";

type Theme = "light" | "dark";
type Ctx = { theme: Theme; toggle: () => void };

const ThemeCtx = createContext<Ctx | null>(null);
const STORAGE_KEY = "niyam-v2-theme";

export function useV2Theme() {
  const ctx = useContext(ThemeCtx);
  if (!ctx) throw new Error("useV2Theme must be used inside V2ThemeProvider");
  return ctx;
}

export function V2ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    const forced = new URL(window.location.href).searchParams.get("theme");
    if (forced === "dark" || forced === "light") {
      setTheme(forced);
      return;
    }
    const stored = window.localStorage.getItem(STORAGE_KEY) as Theme | null;
    if (stored === "dark" || stored === "light") setTheme(stored);
  }, []);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  const toggle = () => setTheme((t) => (t === "dark" ? "light" : "dark"));

  return (
    <div data-theme-v="2" data-theme={theme === "dark" ? "dark" : undefined}>
      <ThemeCtx.Provider value={{ theme, toggle }}>{children}</ThemeCtx.Provider>
    </div>
  );
}
