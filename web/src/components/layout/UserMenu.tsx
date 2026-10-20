import { FolderOpen, LogOut, UserRound } from "lucide-react";
import { useNavigate } from "react-router-dom";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/overlays";
import { useSignOut, useUser } from "@/lib/session";

function initials(name: string) {
  return (
    name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join("") || "?"
  );
}

export function UserMenu() {
  const user = useUser();
  const navigate = useNavigate();
  const signOut = useSignOut();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className="flex size-9 items-center justify-center overflow-hidden rounded-full border bg-muted text-caption font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-label={`Account: ${user.name || user.email}`}
      >
        {user.picture ? (
          <img src={user.picture} alt="" className="size-full object-cover" referrerPolicy="no-referrer" />
        ) : (
          initials(user.name || user.email)
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuLabel>
          <span className="block truncate font-medium">{user.name || "Signed in"}</span>
          <span className="block truncate text-caption font-normal text-muted-foreground">{user.email}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => navigate("/settings/account")}>
          <UserRound /> Account
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => navigate("/settings/storage")}>
          <FolderOpen /> Documents folder
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={signOut}>
          <LogOut /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
