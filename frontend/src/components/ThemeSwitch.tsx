import { Moon, Sun, Monitor } from "lucide-react"
import { useTheme } from "../hooks/useTheme"
export function ThemeSwitch() {
  const { theme, setTheme } = useTheme()
  return <div className="theme-switch" role="group" aria-label="Color theme">{([{ value: "light", label: "Light", icon: Sun }, { value: "dark", label: "Dark", icon: Moon }, { value: "system", label: "System", icon: Monitor }] as const).map(({ value, label, icon: Icon }) => <button type="button" key={value} aria-label={`${label} theme`} aria-pressed={theme === value} title={`${label} theme`} onClick={() => setTheme(value)}><Icon size={15} /></button>)}</div>
}
