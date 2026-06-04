import { useState, useEffect } from "react";

export function useDarkMode() {
  const [isDark, setIsDark] = useState<boolean>(() => {
    const stored = localStorage.getItem("theme");
    return stored ? stored === "dark" : true; // default dark
  });

  useEffect(() => {
    const root = document.documentElement;
    if (isDark) {
      root.classList.add("dark");
    } else {
      root.classList.remove("dark");
    }
    localStorage.setItem("theme", isDark ? "dark" : "light");
  }, [isDark]);

  return [isDark, () => setIsDark((d) => !d)] as const;
}
