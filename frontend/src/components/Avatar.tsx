import { BrandMark } from "./Brand"

export function BotAvatar() {
  return <div className="bot-avatar" aria-hidden="true"><BrandMark /></div>
}

export function UserAvatar({ identifier }: { identifier: string }) {
  const initial = identifier.trim().charAt(0).toUpperCase() || "?"
  return <div className="user-avatar" aria-hidden="true">{initial}</div>
}
