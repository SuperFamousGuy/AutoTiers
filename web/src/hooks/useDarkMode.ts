import { useState, useLayoutEffect } from "react";

function getStoredTheme(): boolean {
  try {
    const stored = localStorage.getItem("theme");
    if (stored === "dark") return true;
    if (stored === "light") return false;
    return true; // default dark
  } catch {
    return true; // storage blocked — default dark
  }
}

export function useDarkMode() {
  const [isDark, setIsDark] = useState<boolean>(getStoredTheme);

  useLayoutEffect(() => {
    document.documentElement.classList.toggle("dark", isDark);
    try {
      localStorage.setItem("theme", isDark ? "dark" : "light");
    } catch {
      // storage blocked — preference not persisted
    }
  }, [isDark]);

  return [isDark, () => setIsDark((d) => !d)] as const;
}
