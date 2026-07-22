import { ShoppingBag } from "lucide-react"

export function BotAvatar() {
  return (
    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand text-white shadow-sm">
      <ShoppingBag size={16} strokeWidth={2.25} />
    </div>
  )
}

export function UserAvatar({ identifier }: { identifier: string }) {
  const initial = identifier.trim().charAt(0).toUpperCase() || "?"
  return (
    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-neutral-700 text-white text-sm font-medium shadow-sm">
      {initial}
    </div>
  )
}
