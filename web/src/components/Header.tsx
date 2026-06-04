import { HelpCircle, Menu, Moon, Sun } from "lucide-react";
import { useState } from "react";
import { DataFreshness } from "./DataFreshness";
import { GenerateButton } from "./GenerateButton";
import { AuthDialog } from "./AuthDialog";
import { FavoritesDialog } from "./FavoritesDialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/contexts/AuthContext";
import type { SettingsState } from "./SettingsPanel";
import type { Rule } from "@/api/types";

interface HamburgerProps {
  currentState: { settings: SettingsState; rules: Rule[] } | null;
  onOpenLinkedAccounts?: () => void;
}

function HamburgerMenu({ currentState, onOpenLinkedAccounts }: HamburgerProps) {
  const { user, logout } = useAuth();
  const [authOpen, setAuthOpen] = useState(false);
  const [favoritesOpen, setFavoritesOpen] = useState(false);

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" aria-label="Menu">
            <Menu className="h-5 w-5" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          {user ? (
            <>
              <DropdownMenuItem disabled>
                {user.email ?? (user.google_subject ? "Google account" : "Yahoo account")}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => onOpenLinkedAccounts?.()}>
                Connect Your League
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => setFavoritesOpen(true)}>Favorites</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => logout()}>Log Out</DropdownMenuItem>
            </>
          ) : (
            <DropdownMenuItem onSelect={() => setAuthOpen(true)}>Log In / Sign Up</DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
      <AuthDialog open={authOpen} onOpenChange={setAuthOpen} initialState={currentState} />
      <FavoritesDialog open={favoritesOpen} onOpenChange={setFavoritesOpen} isLoggedIn={!!user} />
    </>
  );
}

interface HeaderProps {
  generateDisabled: boolean;
  generateIsPending: boolean;
  onGenerate: () => void;
  currentState: { settings: SettingsState; rules: Rule[] } | null;
  profilePicker?: React.ReactNode;
  onOpenLinkedAccounts?: () => void;
  isDark: boolean;
  onToggleDark: () => void;
  onShowOnboarding?: () => void;
}

export function Header({
  generateDisabled, generateIsPending, onGenerate, currentState, profilePicker, onOpenLinkedAccounts, isDark, onToggleDark, onShowOnboarding,
}: HeaderProps) {
  return (
    <header className="flex items-center justify-between border-b bg-card px-6 py-4">
      <div className="flex items-baseline gap-6">
        <h1 className="text-2xl font-bold text-foreground">AutoTiers</h1>
        <DataFreshness />
      </div>
      <div className="flex items-center gap-3">
        {profilePicker}
        <GenerateButton
          disabled={generateDisabled}
          isPending={generateIsPending}
          onClick={onGenerate}
        />
        {onShowOnboarding && (
          <Button variant="ghost" size="icon" aria-label="Show getting-started guide" onClick={onShowOnboarding}>
            <HelpCircle className="h-5 w-5" />
          </Button>
        )}
        <Button variant="ghost" size="icon" aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"} onClick={onToggleDark}>
          {isDark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
        </Button>
        <HamburgerMenu currentState={currentState} onOpenLinkedAccounts={onOpenLinkedAccounts} />
      </div>
    </header>
  );
}
