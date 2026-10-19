import { useEffect, useState } from "react"
export type Theme = "light" | "dark" | "system"
const STORAGE_KEY = "theme"
function readInitial(): Theme {
  try { const value = localStorage.getItem(STORAGE_KEY); return value === "light" || value === "system" || value === "dark" ? value : "dark" } catch { return "dark" }
}
function apply(theme: Theme) { document.documentElement.dataset.theme = theme }
apply(readInitial())
export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(readInitial)
  useEffect(() => {
    const sync = () => { const next = readInitial(); setThemeState(next); apply(next) }
    window.addEventListener("aster-theme", sync)
    window.addEventListener("storage", sync)
    return () => { window.removeEventListener("aster-theme", sync); window.removeEventListener("storage", sync) }
  }, [])
  function setTheme(next: Theme) {
    apply(next); setThemeState(next)
    try { localStorage.setItem(STORAGE_KEY, next) } catch { /* Current session still follows chosen theme. */ }
    window.dispatchEvent(new Event("aster-theme"))
  }
  return { theme, setTheme }
}
