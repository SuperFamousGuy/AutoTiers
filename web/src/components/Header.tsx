import { HelpCircle, Menu, Moon, Sun } from "lucide-react";
import { useState } from "react";
import { DataFreshness } from "./DataFreshness";
import { Logo } from "./Logo";
import { GenerateButton } from "./GenerateButton";
import { FeedbackDialog } from "./FeedbackDialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";

interface HamburgerProps {
  mobileProfileMenu?: React.ReactNode;
  isDark?: boolean;
  onToggleDark?: () => void;
  onShowOnboarding?: () => void;
}

function HamburgerMenu({ mobileProfileMenu, isDark, onToggleDark, onShowOnboarding }: HamburgerProps) {
  const [feedbackOpen, setFeedbackOpen] = useState(false);

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" aria-label="Menu" data-tour="menu">
            <Menu className="h-5 w-5" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          {/* Profile switch/create/manage — mobile only; desktop uses ProfileSwitcher (#499). */}
          {mobileProfileMenu}
          <DropdownMenuItem onSelect={() => setFeedbackOpen(true)}>Provide Feedback</DropdownMenuItem>
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
          <DropdownMenuItem asChild>
            <a href="/terms.html" target="_blank" rel="noopener noreferrer">
              Terms of Service
            </a>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <FeedbackDialog open={feedbackOpen} onOpenChange={setFeedbackOpen} />
    </>
  );
}

interface HeaderProps {
  generateDisabled: boolean;
  generateIsPending: boolean;
  onGenerate: () => void;
  profilePicker?: React.ReactNode;
  isDark: boolean;
  onToggleDark: () => void;
  onShowOnboarding?: () => void;
  mobileProfileMenu?: React.ReactNode;
}

export function Header({
  generateDisabled, generateIsPending, onGenerate, profilePicker, isDark, onToggleDark, onShowOnboarding, mobileProfileMenu,
}: HeaderProps) {
  return (
    <header className="flex items-center justify-between border-b bg-card px-4 py-3 lg:px-6 lg:py-4">
      <div className="flex items-center gap-3 lg:gap-6">
        <h1 className="flex h-8 items-center text-2xl text-foreground">
          <Logo className="h-full" />
        </h1>
        {/* Visible at every width — compact on mobile, full-text on desktop — so
            draft-day users on a phone can still see whether projections are current. */}
        <DataFreshness />
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
          mobileProfileMenu={mobileProfileMenu}
          isDark={isDark}
          onToggleDark={onToggleDark}
          onShowOnboarding={onShowOnboarding}
        />
      </div>
    </header>
  );
}
