import { HelpCircle, Menu, Moon, Sun } from "lucide-react";
import { useState } from "react";
import { DataFreshness } from "./DataFreshness";
import { Logo } from "./Logo";
import { GenerateButton } from "./GenerateButton";
import { AuthDialog } from "./AuthDialog";
import { FavoritesDialog } from "./FavoritesDialog";
import { FeedbackDialog } from "./FeedbackDialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/contexts/AuthContext";
import type { SettingsState } from "./SettingsPanel";
import type { PositionRulesState } from "@/api/types";

interface HamburgerProps {
  currentState: { settings: SettingsState; rules: PositionRulesState } | null;
  onOpenLinkedAccounts?: () => void;
  activeProfileName?: string | null;
  isDark?: boolean;
  onToggleDark?: () => void;
  onShowOnboarding?: () => void;
}

function HamburgerMenu({ currentState, onOpenLinkedAccounts, activeProfileName, isDark, onToggleDark, onShowOnboarding }: HamburgerProps) {
  const { user, logout } = useAuth();
  const [authOpen, setAuthOpen] = useState(false);
  const [favoritesOpen, setFavoritesOpen] = useState(false);
  const [feedbackOpen, setFeedbackOpen] = useState(false);

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
              {activeProfileName && (
                <DropdownMenuItem disabled className="lg:hidden">
                  Profile: {activeProfileName}
                </DropdownMenuItem>
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => onOpenLinkedAccounts?.()}>
                Connect Your League
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => setFavoritesOpen(true)}>Favorites</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => setFeedbackOpen(true)}>Provide Feedback</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => logout()}>Log Out</DropdownMenuItem>
            </>
          ) : (
            <>
              <DropdownMenuItem onSelect={() => setAuthOpen(true)}>Log In / Sign Up</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => setFeedbackOpen(true)}>Provide Feedback</DropdownMenuItem>
            </>
          )}
          {onShowOnboarding && (
            <DropdownMenuItem className="lg:hidden" onSelect={() => onShowOnboarding()}>
              Getting Started Guide
            </DropdownMenuItem>
          )}
          {onToggleDark && (
            <DropdownMenuItem className="lg:hidden" onSelect={() => onToggleDark()}>
              {isDark ? "Switch to Light Mode" : "Switch to Dark Mode"}
            </DropdownMenuItem>
          )}
          <DropdownMenuSeparator />
          <DropdownMenuItem asChild>
            <a href="/privacy.html" target="_blank" rel="noopener noreferrer">
              Privacy Policy
            </a>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <AuthDialog open={authOpen} onOpenChange={setAuthOpen} initialState={currentState} />
      <FavoritesDialog open={favoritesOpen} onOpenChange={setFavoritesOpen} isLoggedIn={!!user} />
      <FeedbackDialog open={feedbackOpen} onOpenChange={setFeedbackOpen} userEmail={user?.email ?? null} />
    </>
  );
}

interface HeaderProps {
  generateDisabled: boolean;
  generateIsPending: boolean;
  onGenerate: () => void;
  currentState: { settings: SettingsState; rules: PositionRulesState } | null;
  profilePicker?: React.ReactNode;
  onOpenLinkedAccounts?: () => void;
  isDark: boolean;
  onToggleDark: () => void;
  onShowOnboarding?: () => void;
  activeProfileName?: string | null;
}

export function Header({
  generateDisabled, generateIsPending, onGenerate, currentState, profilePicker, onOpenLinkedAccounts, isDark, onToggleDark, onShowOnboarding, activeProfileName,
}: HeaderProps) {
  return (
    <header className="flex items-center justify-between border-b bg-card px-4 py-3 lg:px-6 lg:py-4">
      <div className="flex items-center gap-6">
        <h1 className="flex h-8 items-center text-2xl text-foreground">
          <Logo className="h-full" />
        </h1>
        <span className="hidden lg:inline">
          <DataFreshness />
        </span>
      </div>
      <div className="flex items-center gap-3">
        <div className="hidden lg:flex lg:items-center lg:gap-2">
          {profilePicker}
        </div>
        <GenerateButton
          disabled={generateDisabled}
          isPending={generateIsPending}
          onClick={onGenerate}
        />
        {onShowOnboarding && (
          <Button variant="ghost" size="icon" aria-label="Show getting-started guide" onClick={onShowOnboarding} className="hidden lg:inline-flex">
            <HelpCircle className="h-5 w-5" />
          </Button>
        )}
        <Button variant="ghost" size="icon" aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"} onClick={onToggleDark} className="hidden lg:inline-flex">
          {isDark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
        </Button>
        <HamburgerMenu
          currentState={currentState}
          onOpenLinkedAccounts={onOpenLinkedAccounts}
          activeProfileName={activeProfileName}
          isDark={isDark}
          onToggleDark={onToggleDark}
          onShowOnboarding={onShowOnboarding}
        />
      </div>
    </header>
  );
}
