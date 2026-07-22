import { useEffect, useState } from "react"

export type Theme = "light" | "dark" | "system"

const STORAGE_KEY = "theme"

function apply(theme: Theme) {
  const root = document.documentElement
  if (theme === "system") {
    delete root.dataset.theme // falls back to the prefers-color-scheme block in index.css
  } else {
    root.dataset.theme = theme
  }
}

function readInitial(): Theme {
  const stored = localStorage.getItem(STORAGE_KEY)
  return stored === "light" || stored === "dark" || stored === "system" ? stored : "system"
}

// Applied once at module load (before React mounts) so there's no
// flash-of-wrong-theme between first paint and the Sidebar's effect running.
apply(readInitial())

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(readInitial)

  useEffect(() => {
    apply(theme)
    localStorage.setItem(STORAGE_KEY, theme)
  }, [theme])

  return { theme, setTheme: setThemeState }
}
