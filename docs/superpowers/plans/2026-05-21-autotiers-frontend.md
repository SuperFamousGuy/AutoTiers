# AutoTiers Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the three-panel React UI (Settings / Rules / Tiers) that makes AutoTiers a real product instead of a curl demo. Talks to the existing FastAPI backend; produces a tier-banded draft board with downloadable CSV.

**Architecture:** Single-page React app. TanStack Query handles server state (`/api/rules`, `/api/data/status`, `/api/generate`). The form (settings + rules) is local `useState` in `App.tsx`, passed by prop to each panel. shadcn/ui provides accessible primitives (Slider, Switch, Select, Toggle, etc.) built on Radix + Tailwind. A new `web` service joins the existing docker-compose stack for one-command local dev.

**Tech Stack:** React 18, TypeScript, Vite, TanStack Query v5, Tailwind CSS, shadcn/ui (Radix + Tailwind), Vitest, @testing-library/react, MSW v2.

**Prerequisites:**
- Fresh feature branch off `main`: `git checkout main && git pull && git checkout -b frontend`
- Node.js 22+ available on the host (for the initial scaffold; everything afterwards runs inside the Docker container)
- The backend running (you can use `podman compose up db api` to bring just those two up while developing the frontend)

---

## Task 1: Scaffold Vite + React + TypeScript project

**Files:**
- Create: `web/package.json`
- Create: `web/tsconfig.json`
- Create: `web/tsconfig.node.json`
- Create: `web/vite.config.ts`
- Create: `web/index.html`
- Create: `web/src/main.tsx`
- Create: `web/src/App.tsx`
- Create: `web/src/index.css`
- Create: `web/.gitignore`

- [ ] **Step 1: Create the `web/` directory and initial files**

```bash
cd /Users/karlkell/Code/AutoTiers && mkdir -p web/src
```

Create `web/package.json`:

```json
{
  "name": "autotiers-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "@tanstack/react-query": "^5.51.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "typescript": "^5.5.3",
    "vite": "^5.3.4",
    "vitest": "^2.0.4",
    "@testing-library/react": "^16.0.0",
    "@testing-library/jest-dom": "^6.4.6",
    "@testing-library/user-event": "^14.5.2",
    "jsdom": "^24.1.1",
    "msw": "^2.3.4"
  }
}
```

Create `web/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    },
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

Create `web/tsconfig.node.json`:

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true
  },
  "include": ["vite.config.ts"]
}
```

Create `web/vite.config.ts`:

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/tests/setup.ts"],
  },
});
```

Create `web/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>AutoTiers — Fantasy Football Draft Tier Generator</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

Create `web/src/main.tsx`:

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false } },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
```

Create `web/src/App.tsx` (minimal placeholder for now):

```tsx
export default function App() {
  return <div className="p-8">AutoTiers</div>;
}
```

Create `web/src/index.css` (Tailwind imports come in Task 2; minimal for now):

```css
body {
  margin: 0;
  font-family: system-ui, -apple-system, sans-serif;
}
```

Create `web/.gitignore`:

```
node_modules
dist
*.log
.env.local
.vite
coverage
```

- [ ] **Step 2: Install dependencies**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npm install
```

Expected: lockfile created, `node_modules` populated. Should take 30-60s.

- [ ] **Step 3: Verify dev server starts**

```bash
npm run dev
```

Expected: prints `VITE v5.x ready in Nms` and `Local: http://localhost:5173/`. Open the URL in a browser — should see "AutoTiers". Stop the server (Ctrl-C).

- [ ] **Step 4: Verify build works**

```bash
npm run build
```

Expected: TypeScript compiles, Vite builds to `dist/`, no errors.

- [ ] **Step 5: Commit**

```bash
cd /Users/karlkell/Code/AutoTiers && git add web/ && git commit -m "feat(web): scaffold Vite + React + TypeScript project"
```

---

## Task 2: Tailwind + shadcn/ui setup

**Files:**
- Modify: `web/package.json` (new deps)
- Create: `web/tailwind.config.ts`
- Create: `web/postcss.config.js`
- Create: `web/components.json`
- Modify: `web/src/index.css` (Tailwind imports + CSS vars)
- Modify: `web/src/App.tsx` (use Tailwind classes)
- Create: `web/src/lib/utils.ts` (shadcn helper)
- Create: shadcn primitive components in `web/src/components/ui/`

- [ ] **Step 1: Install Tailwind + shadcn deps**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npm install -D tailwindcss@^3.4.7 postcss@^8.4.40 autoprefixer@^10.4.19 && npm install class-variance-authority@^0.7.0 clsx@^2.1.1 tailwind-merge@^2.4.0 lucide-react@^0.408.0 tailwindcss-animate@^1.0.7 @radix-ui/react-slot@^1.1.0
```

- [ ] **Step 2: Create `web/postcss.config.js`**

```js
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 3: Create `web/tailwind.config.ts`**

Use the standard shadcn/ui Tailwind config:

```ts
import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: { center: true, padding: "2rem", screens: { "2xl": "1400px" } },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [animate],
} satisfies Config;
```

- [ ] **Step 4: Replace `web/src/index.css` with Tailwind + shadcn CSS vars**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 222.2 84% 4.9%;
    --card: 0 0% 100%;
    --card-foreground: 222.2 84% 4.9%;
    --primary: 222.2 47.4% 11.2%;
    --primary-foreground: 210 40% 98%;
    --secondary: 210 40% 96.1%;
    --secondary-foreground: 222.2 47.4% 11.2%;
    --muted: 210 40% 96.1%;
    --muted-foreground: 215.4 16.3% 46.9%;
    --accent: 210 40% 96.1%;
    --accent-foreground: 222.2 47.4% 11.2%;
    --destructive: 0 84.2% 60.2%;
    --destructive-foreground: 210 40% 98%;
    --border: 214.3 31.8% 91.4%;
    --input: 214.3 31.8% 91.4%;
    --ring: 222.2 84% 4.9%;
    --radius: 0.5rem;
  }
  body {
    @apply bg-background text-foreground;
  }
}
```

- [ ] **Step 5: Create `web/components.json` (shadcn config)**

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "default",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "tailwind.config.ts",
    "css": "src/index.css",
    "baseColor": "slate",
    "cssVariables": true
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils"
  }
}
```

- [ ] **Step 6: Create `web/src/lib/utils.ts`**

```ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

- [ ] **Step 7: Install Radix primitives needed for our components**

These power the shadcn components we'll use. Installing them upfront avoids per-component installs later.

```bash
cd /Users/karlkell/Code/AutoTiers/web && npm install @radix-ui/react-label@^2.1.0 @radix-ui/react-radio-group@^1.2.0 @radix-ui/react-select@^2.1.1 @radix-ui/react-slider@^1.2.0 @radix-ui/react-switch@^1.1.0 @radix-ui/react-toggle-group@^1.1.0 @radix-ui/react-collapsible@^1.1.0 @radix-ui/react-toast@^1.2.0 @radix-ui/react-tooltip@^1.1.2
```

- [ ] **Step 8: Add shadcn components**

shadcn doesn't ship as a runtime library — its CLI copies source into your repo. Create the directory and add each component file by hand based on the shadcn templates. Create `web/src/components/ui/` and the following files:

Create `web/src/components/ui/button.tsx`:

```tsx
import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        outline: "border border-input bg-background hover:bg-accent hover:text-accent-foreground",
        secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost: "hover:bg-accent hover:text-accent-foreground",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-md px-3",
        lg: "h-11 rounded-md px-8",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
  },
);
Button.displayName = "Button";

export { buttonVariants };
```

Create `web/src/components/ui/slider.tsx`:

```tsx
import * as React from "react";
import * as SliderPrimitive from "@radix-ui/react-slider";
import { cn } from "@/lib/utils";

export const Slider = React.forwardRef<
  React.ElementRef<typeof SliderPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof SliderPrimitive.Root>
>(({ className, ...props }, ref) => (
  <SliderPrimitive.Root
    ref={ref}
    className={cn("relative flex w-full touch-none select-none items-center", className)}
    {...props}
  >
    <SliderPrimitive.Track className="relative h-2 w-full grow overflow-hidden rounded-full bg-secondary">
      <SliderPrimitive.Range className="absolute h-full bg-primary" />
    </SliderPrimitive.Track>
    <SliderPrimitive.Thumb className="block h-5 w-5 rounded-full border-2 border-primary bg-background ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50" />
  </SliderPrimitive.Root>
));
Slider.displayName = SliderPrimitive.Root.displayName;
```

Create `web/src/components/ui/switch.tsx`:

```tsx
import * as React from "react";
import * as SwitchPrimitive from "@radix-ui/react-switch";
import { cn } from "@/lib/utils";

export const Switch = React.forwardRef<
  React.ElementRef<typeof SwitchPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof SwitchPrimitive.Root>
>(({ className, ...props }, ref) => (
  <SwitchPrimitive.Root
    ref={ref}
    className={cn(
      "peer inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:bg-primary data-[state=unchecked]:bg-input",
      className,
    )}
    {...props}
  >
    <SwitchPrimitive.Thumb className="pointer-events-none block h-5 w-5 rounded-full bg-background shadow-lg ring-0 transition-transform data-[state=checked]:translate-x-5 data-[state=unchecked]:translate-x-0" />
  </SwitchPrimitive.Root>
));
Switch.displayName = SwitchPrimitive.Root.displayName;
```

Create `web/src/components/ui/select.tsx`:

```tsx
import * as React from "react";
import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

export const Select = SelectPrimitive.Root;
export const SelectValue = SelectPrimitive.Value;

export const SelectTrigger = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Trigger>
>(({ className, children, ...props }, ref) => (
  <SelectPrimitive.Trigger
    ref={ref}
    className={cn(
      "flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
      className,
    )}
    {...props}
  >
    {children}
    <SelectPrimitive.Icon asChild>
      <ChevronDown className="h-4 w-4 opacity-50" />
    </SelectPrimitive.Icon>
  </SelectPrimitive.Trigger>
));
SelectTrigger.displayName = SelectPrimitive.Trigger.displayName;

export const SelectContent = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Content>
>(({ className, children, position = "popper", ...props }, ref) => (
  <SelectPrimitive.Portal>
    <SelectPrimitive.Content
      ref={ref}
      className={cn(
        "relative z-50 max-h-96 min-w-[8rem] overflow-hidden rounded-md border bg-popover text-popover-foreground shadow-md data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
        position === "popper" && "data-[side=bottom]:translate-y-1",
        className,
      )}
      position={position}
      {...props}
    >
      <SelectPrimitive.Viewport
        className={cn("p-1", position === "popper" && "h-[var(--radix-select-trigger-height)] w-full min-w-[var(--radix-select-trigger-width)]")}
      >
        {children}
      </SelectPrimitive.Viewport>
    </SelectPrimitive.Content>
  </SelectPrimitive.Portal>
));
SelectContent.displayName = SelectPrimitive.Content.displayName;

export const SelectItem = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Item>
>(({ className, children, ...props }, ref) => (
  <SelectPrimitive.Item
    ref={ref}
    className={cn(
      "relative flex w-full cursor-default select-none items-center rounded-sm py-1.5 pl-8 pr-2 text-sm outline-none focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
      className,
    )}
    {...props}
  >
    <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
      <SelectPrimitive.ItemIndicator>
        <Check className="h-4 w-4" />
      </SelectPrimitive.ItemIndicator>
    </span>
    <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
  </SelectPrimitive.Item>
));
SelectItem.displayName = SelectPrimitive.Item.displayName;
```

Create `web/src/components/ui/radio-group.tsx`:

```tsx
import * as React from "react";
import * as RadioGroupPrimitive from "@radix-ui/react-radio-group";
import { Circle } from "lucide-react";
import { cn } from "@/lib/utils";

export const RadioGroup = React.forwardRef<
  React.ElementRef<typeof RadioGroupPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof RadioGroupPrimitive.Root>
>(({ className, ...props }, ref) => (
  <RadioGroupPrimitive.Root className={cn("grid gap-2", className)} ref={ref} {...props} />
));
RadioGroup.displayName = RadioGroupPrimitive.Root.displayName;

export const RadioGroupItem = React.forwardRef<
  React.ElementRef<typeof RadioGroupPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof RadioGroupPrimitive.Item>
>(({ className, ...props }, ref) => (
  <RadioGroupPrimitive.Item
    ref={ref}
    className={cn(
      "aspect-square h-4 w-4 rounded-full border border-primary text-primary ring-offset-background focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
      className,
    )}
    {...props}
  >
    <RadioGroupPrimitive.Indicator className="flex items-center justify-center">
      <Circle className="h-2.5 w-2.5 fill-current text-current" />
    </RadioGroupPrimitive.Indicator>
  </RadioGroupPrimitive.Item>
));
RadioGroupItem.displayName = RadioGroupPrimitive.Item.displayName;
```

Create `web/src/components/ui/toggle-group.tsx`:

```tsx
import * as React from "react";
import * as ToggleGroupPrimitive from "@radix-ui/react-toggle-group";
import { cn } from "@/lib/utils";

export const ToggleGroup = ToggleGroupPrimitive.Root;

export const ToggleGroupItem = React.forwardRef<
  React.ElementRef<typeof ToggleGroupPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof ToggleGroupPrimitive.Item>
>(({ className, children, ...props }, ref) => (
  <ToggleGroupPrimitive.Item
    ref={ref}
    className={cn(
      "inline-flex h-8 items-center justify-center rounded-md px-3 text-xs font-medium ring-offset-background transition-colors hover:bg-muted hover:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 data-[state=on]:bg-primary data-[state=on]:text-primary-foreground border border-input",
      className,
    )}
    {...props}
  >
    {children}
  </ToggleGroupPrimitive.Item>
));
ToggleGroupItem.displayName = ToggleGroupPrimitive.Item.displayName;
```

Create `web/src/components/ui/label.tsx`:

```tsx
import * as React from "react";
import * as LabelPrimitive from "@radix-ui/react-label";
import { cn } from "@/lib/utils";

export const Label = React.forwardRef<
  React.ElementRef<typeof LabelPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof LabelPrimitive.Root>
>(({ className, ...props }, ref) => (
  <LabelPrimitive.Root
    ref={ref}
    className={cn("text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70", className)}
    {...props}
  />
));
Label.displayName = LabelPrimitive.Root.displayName;
```

Create `web/src/components/ui/collapsible.tsx`:

```tsx
import * as CollapsiblePrimitive from "@radix-ui/react-collapsible";

export const Collapsible = CollapsiblePrimitive.Root;
export const CollapsibleTrigger = CollapsiblePrimitive.CollapsibleTrigger;
export const CollapsibleContent = CollapsiblePrimitive.CollapsibleContent;
```

Create `web/src/components/ui/tooltip.tsx`:

```tsx
import * as React from "react";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { cn } from "@/lib/utils";

export const TooltipProvider = TooltipPrimitive.Provider;
export const Tooltip = TooltipPrimitive.Root;
export const TooltipTrigger = TooltipPrimitive.Trigger;

export const TooltipContent = React.forwardRef<
  React.ElementRef<typeof TooltipPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TooltipPrimitive.Content>
>(({ className, sideOffset = 4, ...props }, ref) => (
  <TooltipPrimitive.Content
    ref={ref}
    sideOffset={sideOffset}
    className={cn(
      "z-50 overflow-hidden rounded-md border bg-popover px-3 py-1.5 text-sm text-popover-foreground shadow-md",
      className,
    )}
    {...props}
  />
));
TooltipContent.displayName = TooltipPrimitive.Content.displayName;
```

The other shadcn ui pieces we need (popover, dropdown) — defer to later tasks as needed.

- [ ] **Step 9: Update `web/src/App.tsx` to verify Tailwind works**

```tsx
import { Button } from "@/components/ui/button";

export default function App() {
  return (
    <div className="min-h-screen bg-background p-8">
      <h1 className="text-3xl font-bold text-foreground">AutoTiers</h1>
      <p className="mt-2 text-muted-foreground">Fantasy Football Draft Tier Generator</p>
      <Button className="mt-4">Test Button</Button>
    </div>
  );
}
```

- [ ] **Step 10: Verify in browser**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npm run dev
```

Open http://localhost:5173 — should show "AutoTiers" with Tailwind styling and a styled Button below. Stop the dev server.

- [ ] **Step 11: Commit**

```bash
cd /Users/karlkell/Code/AutoTiers && git add web/ && git commit -m "feat(web): Tailwind + shadcn/ui setup with core primitives"
```

---

## Task 3: Docker integration

**Files:**
- Create: `web/Dockerfile`
- Create: `web/.dockerignore`
- Modify: `docker-compose.yml`
- Modify: `.env.example`

- [ ] **Step 1: Create `web/Dockerfile`**

```dockerfile
FROM node:22-alpine
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

- [ ] **Step 2: Create `web/.dockerignore`**

```
node_modules
dist
.vite
coverage
.env.local
*.log
.git
```

- [ ] **Step 3: Modify `docker-compose.yml` — add `web` service**

Read the existing file first. Append a new `web` service inside the `services:` block (after `api`), and don't change existing services. The new block:

```yaml
  web:
    build:
      context: ./web
      dockerfile: Dockerfile
    container_name: autotiers-web
    depends_on:
      - api
    ports:
      - "${WEB_PORT:-5173}:5173"
    environment:
      VITE_API_URL: "http://localhost:${API_PORT:-8000}"
    volumes:
      - ./web/src:/app/src
      - ./web/public:/app/public
      - ./web/index.html:/app/index.html
      - ./web/tailwind.config.ts:/app/tailwind.config.ts
      - ./web/components.json:/app/components.json
```

(The volumes only mount source/config — `node_modules` stays in the image so `npm install` doesn't have to run on every reboot.)

- [ ] **Step 4: Modify `.env.example` — add `WEB_PORT`**

Append to `.env.example`:

```

WEB_PORT=5173
```

- [ ] **Step 5: Verify the stack builds and starts**

```bash
cd /Users/karlkell/Code/AutoTiers && podman compose down -v && podman compose up --build -d
podman ps
```

Expected: three containers running (`autotiers-db`, `autotiers-api`, `autotiers-web`). Check the web container's logs:

```bash
podman logs autotiers-web | tail -10
```

Expected: `VITE v5.x ready` and `Network: http://0.0.0.0:5173/`.

Open http://localhost:5173 — should still show the "AutoTiers" page with the test button.

- [ ] **Step 6: Commit**

```bash
git add web/Dockerfile web/.dockerignore docker-compose.yml .env.example
git commit -m "feat(web): docker-compose web service with hot-reload mounts"
```

---

## Task 4: API types + client + hooks

**Files:**
- Create: `web/src/api/types.ts`
- Create: `web/src/api/client.ts`
- Create: `web/src/api/hooks.ts`

- [ ] **Step 1: Create `web/src/api/types.ts`**

These mirror the backend's Pydantic schemas. Source of truth: `backend/app/schemas/*.py`. Keep in sync.

```ts
export type ScoringFormat = "standard" | "half_ppr" | "ppr" | "te_premium";
export type LeagueType = "standard" | "dynasty" | "keeper";
export type LeagueSize = 8 | 10 | 12 | 14 | 16;
export type QbTdPoints = 4 | 6;

export type RuleOperator = ">" | ">=" | "<" | "<=" | "==" | "!=";
export type EffectType = "multiplier" | "flat_bonus" | "flat_penalty" | "flag";

export interface RuleCondition {
  field: string;
  operator: RuleOperator;
  value: number | string | boolean;
}

export interface RuleEffect {
  type: EffectType;
  value: number | string;
}

export interface Rule {
  name: string;
  conditions: RuleCondition[];
  effect: RuleEffect;
  enabled: boolean;
  weight: number; // 0.5 | 1.0 | 2.0
  is_builtin: boolean;
  category: string;
}

export interface GenerateRequest {
  scoring_format: ScoringFormat;
  league_type: LeagueType;
  league_size: LeagueSize;
  qb_td_points: QbTdPoints;
  bonus_100yd_rushing: boolean;
  bonus_100yd_receiving: boolean;
  bonus_first_downs: boolean;
  weight_prior_year: number;
  weight_espn: number;
  weight_consensus: number;
  rules: Rule[];
}

export interface TieredPlayer {
  overall_rank: number;
  player_id: string;
  name: string;
  position: string;
  team: string | null;
  age: number | null;
  overall_tier: number;
  positional_tier: string;
  adjusted_score: number;
  projected_score_raw: number;
  prior_year_actual: number | null;
  adp_standard: number | null;
  adp_ppr: number | null;
  adp_dynasty: number | null;
  flags: string[];
  rules_applied: string[];
}

export interface GenerateResponse {
  players: TieredPlayer[];
  total: number;
  data_as_of: string | null;
}

export interface DataSourceStatus {
  last_updated: string | null;
  last_attempted: string | null;
  last_error: string | null;
  rows_upserted: number;
}

export type DataStatusResponse = Record<string, DataSourceStatus>;
```

- [ ] **Step 2: Create `web/src/api/client.ts`**

```ts
export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new ApiError(resp.status, body || resp.statusText);
  }
  return resp.json() as Promise<T>;
}
```

- [ ] **Step 3: Create `web/src/api/hooks.ts`**

```ts
import { useMutation, useQuery } from "@tanstack/react-query";
import { apiFetch, API_URL } from "./client";
import type {
  DataStatusResponse,
  GenerateRequest,
  GenerateResponse,
  Rule,
} from "./types";

export function useRules() {
  return useQuery<Rule[]>({
    queryKey: ["rules"],
    queryFn: () => apiFetch<Rule[]>("/api/rules"),
    staleTime: Infinity,
  });
}

export function useDataStatus() {
  return useQuery<DataStatusResponse>({
    queryKey: ["data-status"],
    queryFn: () => apiFetch<DataStatusResponse>("/api/data/status"),
    staleTime: 60_000,
  });
}

export function useGenerateMutation() {
  return useMutation<GenerateResponse, Error, GenerateRequest>({
    mutationFn: (body) =>
      apiFetch<GenerateResponse>("/api/generate", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
}

export async function downloadCsv(body: GenerateRequest): Promise<void> {
  const resp = await fetch(`${API_URL}/api/generate/csv`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`CSV download failed: ${resp.status}`);
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "tiers.csv";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
```

- [ ] **Step 4: Verify it typechecks**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
cd /Users/karlkell/Code/AutoTiers && git add web/src/api/ && git commit -m "feat(web): API types, client, and TanStack Query hooks"
```

---

## Task 5: Test setup (Vitest + MSW + fixtures)

**Files:**
- Create: `web/src/tests/setup.ts`
- Create: `web/src/tests/handlers.ts`
- Create: `web/src/tests/fixtures/rules.json`
- Create: `web/src/tests/fixtures/data-status.json`
- Create: `web/src/tests/fixtures/generate-response.json`

- [ ] **Step 1: Create `web/src/tests/setup.ts`**

```ts
import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";
import { setupServer } from "msw/node";
import { handlers } from "./handlers";

export const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

- [ ] **Step 2: Create test fixtures**

`web/src/tests/fixtures/rules.json`:

```json
[
  {
    "name": "RB Age Penalty (28-29)",
    "conditions": [{"field": "age", "operator": ">=", "value": 28}],
    "effect": {"type": "multiplier", "value": 0.92},
    "enabled": true,
    "weight": 1.0,
    "is_builtin": true,
    "category": "Age/Longevity"
  },
  {
    "name": "Target Share Premium",
    "conditions": [{"field": "target_share", "operator": ">=", "value": 0.25}],
    "effect": {"type": "flat_bonus", "value": 20.0},
    "enabled": true,
    "weight": 1.0,
    "is_builtin": true,
    "category": "Usage"
  },
  {
    "name": "Handcuff RB Flag",
    "conditions": [{"field": "carry_share", "operator": "<", "value": 0.3}],
    "effect": {"type": "flag", "value": "Handcuff"},
    "enabled": true,
    "weight": 1.0,
    "is_builtin": true,
    "category": "Flag"
  }
]
```

`web/src/tests/fixtures/data-status.json`:

```json
{
  "sleeper": {
    "last_updated": "2026-05-20T03:00:00",
    "last_attempted": "2026-05-20T03:00:00",
    "last_error": null,
    "rows_upserted": 993
  },
  "nfl_data_py": {
    "last_updated": "2026-05-20T03:00:12",
    "last_attempted": "2026-05-20T03:00:12",
    "last_error": null,
    "rows_upserted": 412
  },
  "espn": {
    "last_updated": null,
    "last_attempted": "2026-05-20T03:00:09",
    "last_error": "HTTP 503",
    "rows_upserted": 0
  },
  "fantasypros": {
    "last_updated": "2026-05-20T03:00:15",
    "last_attempted": "2026-05-20T03:00:15",
    "last_error": null,
    "rows_upserted": 2734
  }
}
```

`web/src/tests/fixtures/generate-response.json`:

```json
{
  "total": 5,
  "data_as_of": "2026-05-20",
  "players": [
    {
      "overall_rank": 1,
      "player_id": "6794",
      "name": "Ja'Marr Chase",
      "position": "WR",
      "team": "CIN",
      "age": 26,
      "overall_tier": 1,
      "positional_tier": "WR1",
      "adjusted_score": 385.2,
      "projected_score_raw": 372.0,
      "prior_year_actual": 399.8,
      "adp_standard": 3.0,
      "adp_ppr": 1.5,
      "adp_dynasty": 1.0,
      "flags": ["Contract Year"],
      "rules_applied": ["Target Share Premium", "TD Regression (positive)"]
    },
    {
      "overall_rank": 2,
      "player_id": "8112",
      "name": "Bijan Robinson",
      "position": "RB",
      "team": "ATL",
      "age": 23,
      "overall_tier": 1,
      "positional_tier": "RB1",
      "adjusted_score": 378.4,
      "projected_score_raw": 365.0,
      "prior_year_actual": 320.0,
      "adp_standard": 2.0,
      "adp_ppr": 3.0,
      "adp_dynasty": 3.0,
      "flags": [],
      "rules_applied": ["Red Zone Usage Premium"]
    },
    {
      "overall_rank": 3,
      "player_id": "6786",
      "name": "Justin Jefferson",
      "position": "WR",
      "team": "MIN",
      "age": 27,
      "overall_tier": 2,
      "positional_tier": "WR2",
      "adjusted_score": 354.1,
      "projected_score_raw": 354.1,
      "prior_year_actual": 360.0,
      "adp_standard": 4.0,
      "adp_ppr": 2.5,
      "adp_dynasty": 2.0,
      "flags": [],
      "rules_applied": []
    },
    {
      "overall_rank": 4,
      "player_id": "4866",
      "name": "Saquon Barkley",
      "position": "RB",
      "team": "PHI",
      "age": 28,
      "overall_tier": 2,
      "positional_tier": "RB2",
      "adjusted_score": 340.0,
      "projected_score_raw": 350.0,
      "prior_year_actual": 332.0,
      "adp_standard": 4.0,
      "adp_ppr": 6.0,
      "adp_dynasty": 22.0,
      "flags": [],
      "rules_applied": ["RB Age Penalty (28-29)"]
    },
    {
      "overall_rank": 5,
      "player_id": "4017",
      "name": "Josh Allen",
      "position": "QB",
      "team": "BUF",
      "age": 29,
      "overall_tier": 2,
      "positional_tier": "QB1",
      "adjusted_score": 320.0,
      "projected_score_raw": 320.0,
      "prior_year_actual": 388.0,
      "adp_standard": 17.0,
      "adp_ppr": 18.0,
      "adp_dynasty": 12.0,
      "flags": [],
      "rules_applied": []
    }
  ]
}
```

- [ ] **Step 3: Create `web/src/tests/handlers.ts`**

```ts
import { http, HttpResponse } from "msw";
import rules from "./fixtures/rules.json";
import dataStatus from "./fixtures/data-status.json";
import generateResponse from "./fixtures/generate-response.json";

const API_URL = "http://localhost:8000";

export const handlers = [
  http.get(`${API_URL}/api/rules`, () => HttpResponse.json(rules)),
  http.get(`${API_URL}/api/data/status`, () => HttpResponse.json(dataStatus)),
  http.post(`${API_URL}/api/generate`, () => HttpResponse.json(generateResponse)),
  http.post(`${API_URL}/api/generate/csv`, () =>
    new HttpResponse("rank,name\n1,Chase\n", {
      headers: { "Content-Type": "text/csv" },
    }),
  ),
];
```

- [ ] **Step 4: Write a sanity test to verify the setup**

Create `web/src/tests/setup.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { apiFetch } from "@/api/client";
import type { Rule } from "@/api/types";

describe("MSW setup", () => {
  it("intercepts API calls and returns fixture data", async () => {
    const rules = await apiFetch<Rule[]>("/api/rules");
    expect(rules).toHaveLength(3);
    expect(rules[0].name).toBe("RB Age Penalty (28-29)");
  });
});
```

- [ ] **Step 5: Run the test**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npm test
```

Expected: PASS. 1 test passed.

- [ ] **Step 6: Commit**

```bash
cd /Users/karlkell/Code/AutoTiers && git add web/src/tests/ && git commit -m "feat(web): Vitest + MSW test setup with API fixtures"
```

---

## Task 6: Linked weight redistribution logic (TDD)

**Files:**
- Create: `web/src/lib/weights.ts`
- Create: `web/src/tests/lib/weights.test.ts`

- [ ] **Step 1: Write failing tests**

Create `web/src/tests/lib/weights.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { redistribute, weightsAreValid } from "@/lib/weights";

describe("redistribute", () => {
  it("keeps the sum at 100 when balanced", () => {
    const result = redistribute("prior", 50, { prior: 40, espn: 30, consensus: 30 });
    expect(result.prior + result.espn + result.consensus).toBe(100);
  });

  it("distributes the delta proportionally when others are balanced", () => {
    const result = redistribute("prior", 50, { prior: 40, espn: 30, consensus: 30 });
    // prior gained 10, others lose 10 split 50/50
    expect(result.prior).toBe(50);
    expect(result.espn).toBe(25);
    expect(result.consensus).toBe(25);
  });

  it("distributes proportionally when others are unbalanced", () => {
    // espn 60, consensus 20 (3:1 ratio). prior moves from 20 to 40. Others lose 20.
    // espn loses (60/80)*20 = 15 → 45; consensus loses (20/80)*20 = 5 → 15.
    const result = redistribute("prior", 40, { prior: 20, espn: 60, consensus: 20 });
    expect(result.prior).toBe(40);
    expect(result.espn).toBe(45);
    expect(result.consensus).toBe(15);
    expect(result.prior + result.espn + result.consensus).toBe(100);
  });

  it("splits evenly when both others are zero", () => {
    const result = redistribute("prior", 80, { prior: 100, espn: 0, consensus: 0 });
    expect(result.prior).toBe(80);
    // 20 to split between two zeroes — split evenly
    expect(result.espn + result.consensus).toBe(20);
    expect(Math.abs(result.espn - result.consensus)).toBeLessThanOrEqual(1);
  });

  it("changing espn redistributes prior + consensus", () => {
    const result = redistribute("espn", 50, { prior: 40, espn: 30, consensus: 30 });
    expect(result.espn).toBe(50);
    expect(result.prior + result.consensus).toBe(50);
  });

  it("changing consensus redistributes prior + espn", () => {
    const result = redistribute("consensus", 50, { prior: 40, espn: 30, consensus: 30 });
    expect(result.consensus).toBe(50);
    expect(result.prior + result.espn).toBe(50);
  });

  it("clamps to integer values (no floating-point drift)", () => {
    const result = redistribute("prior", 33, { prior: 50, espn: 25, consensus: 25 });
    expect(Number.isInteger(result.prior)).toBe(true);
    expect(Number.isInteger(result.espn)).toBe(true);
    expect(Number.isInteger(result.consensus)).toBe(true);
    expect(result.prior + result.espn + result.consensus).toBe(100);
  });
});

describe("weightsAreValid", () => {
  it("returns true when weights sum to 100", () => {
    expect(weightsAreValid({ prior: 40, espn: 30, consensus: 30 })).toBe(true);
  });

  it("returns false when weights don't sum to 100", () => {
    expect(weightsAreValid({ prior: 40, espn: 30, consensus: 31 })).toBe(false);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npm test
```

Expected: FAIL — `@/lib/weights` doesn't exist.

- [ ] **Step 3: Create `web/src/lib/weights.ts`**

```ts
export interface Weights {
  prior: number;
  espn: number;
  consensus: number;
}

export type WeightKey = keyof Weights;

/**
 * Adjust one weight to `newValue` and redistribute the delta to the other two
 * proportionally. Returns integer values that always sum to 100.
 */
export function redistribute(
  changed: WeightKey,
  newValue: number,
  current: Weights,
): Weights {
  const others: WeightKey[] =
    changed === "prior"
      ? ["espn", "consensus"]
      : changed === "espn"
      ? ["prior", "consensus"]
      : ["prior", "espn"];

  const remaining = 100 - newValue;
  const oldOtherSum = current[others[0]] + current[others[1]];

  let a: number;
  let b: number;

  if (oldOtherSum === 0) {
    a = Math.floor(remaining / 2);
    b = remaining - a;
  } else {
    a = Math.round((current[others[0]] / oldOtherSum) * remaining);
    b = remaining - a;
  }

  return {
    ...current,
    [changed]: newValue,
    [others[0]]: a,
    [others[1]]: b,
  };
}

export function weightsAreValid(w: Weights): boolean {
  return w.prior + w.espn + w.consensus === 100;
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npm test
```

Expected: all 8 tests pass.

- [ ] **Step 5: Commit**

```bash
cd /Users/karlkell/Code/AutoTiers && git add web/src/lib/weights.ts web/src/tests/lib/ && git commit -m "feat(web): linked weight redistribution logic with TDD"
```

---

## Task 7: Format utilities

**Files:**
- Create: `web/src/lib/format.ts`
- Create: `web/src/tests/lib/format.test.ts`

- [ ] **Step 1: Write failing tests**

Create `web/src/tests/lib/format.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { relativeTime, freshnessLevel } from "@/lib/format";

describe("relativeTime", () => {
  const now = new Date("2026-05-21T12:00:00Z");

  it("returns 'just now' for under 1 minute", () => {
    expect(relativeTime("2026-05-21T11:59:30Z", now)).toBe("just now");
  });

  it("returns minutes for under 1 hour", () => {
    expect(relativeTime("2026-05-21T11:30:00Z", now)).toBe("30 minutes ago");
  });

  it("returns hours for under 1 day", () => {
    expect(relativeTime("2026-05-21T09:00:00Z", now)).toBe("3 hours ago");
  });

  it("returns days for under 1 week", () => {
    expect(relativeTime("2026-05-19T12:00:00Z", now)).toBe("2 days ago");
  });

  it("returns weeks for older", () => {
    expect(relativeTime("2026-05-01T12:00:00Z", now)).toBe("3 weeks ago");
  });

  it("returns 'unknown' for null", () => {
    expect(relativeTime(null, now)).toBe("unknown");
  });
});

describe("freshnessLevel", () => {
  const now = new Date("2026-05-21T12:00:00Z");

  it("returns 'fresh' for under 3 days", () => {
    expect(freshnessLevel("2026-05-20T12:00:00Z", now)).toBe("fresh");
  });

  it("returns 'stale' for 3-7 days", () => {
    expect(freshnessLevel("2026-05-17T12:00:00Z", now)).toBe("stale");
  });

  it("returns 'old' for >7 days", () => {
    expect(freshnessLevel("2026-05-10T12:00:00Z", now)).toBe("old");
  });

  it("returns 'unknown' for null", () => {
    expect(freshnessLevel(null, now)).toBe("unknown");
  });
});
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npm test
```

Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Create `web/src/lib/format.ts`**

```ts
export function relativeTime(iso: string | null, now: Date = new Date()): string {
  if (!iso) return "unknown";
  const then = new Date(iso);
  const diffMs = now.getTime() - then.getTime();
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} day${days === 1 ? "" : "s"} ago`;
  const weeks = Math.floor(days / 7);
  return `${weeks} week${weeks === 1 ? "" : "s"} ago`;
}

export type Freshness = "fresh" | "stale" | "old" | "unknown";

export function freshnessLevel(iso: string | null, now: Date = new Date()): Freshness {
  if (!iso) return "unknown";
  const ageMs = now.getTime() - new Date(iso).getTime();
  const days = ageMs / 86_400_000;
  if (days < 3) return "fresh";
  if (days <= 7) return "stale";
  return "old";
}
```

- [ ] **Step 4: Run to verify they pass**

```bash
npm test
```

Expected: all format tests pass.

- [ ] **Step 5: Commit**

```bash
cd /Users/karlkell/Code/AutoTiers && git add web/src/lib/format.ts web/src/tests/lib/format.test.ts && git commit -m "feat(web): relative time and freshness level helpers"
```

---

## Task 8: Header + DataFreshness + GenerateButton

**Files:**
- Create: `web/src/components/Header.tsx`
- Create: `web/src/components/DataFreshness.tsx`
- Create: `web/src/components/GenerateButton.tsx`
- Create: `web/src/tests/components/DataFreshness.test.tsx`

- [ ] **Step 1: Write a failing test for DataFreshness**

Create `web/src/tests/components/DataFreshness.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DataFreshness } from "@/components/DataFreshness";

function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("DataFreshness", () => {
  it("renders 'Loading data status…' while fetching", async () => {
    renderWithClient(<DataFreshness />);
    expect(screen.getByText(/loading data status/i)).toBeInTheDocument();
  });

  it("renders the oldest source's relative time after load", async () => {
    renderWithClient(<DataFreshness />);
    // ESPN has last_updated=null but last_attempted; we want the oldest of those with a last_updated.
    // sleeper, nfl_data_py, fantasypros all have 2026-05-20 timestamps.
    // Wait for the text to appear.
    expect(await screen.findByText(/data updated/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npm test
```

Expected: FAIL — `@/components/DataFreshness` doesn't exist.

- [ ] **Step 3: Create `web/src/components/DataFreshness.tsx`**

```tsx
import { useDataStatus } from "@/api/hooks";
import { relativeTime, freshnessLevel } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

export function DataFreshness() {
  const { data, isLoading } = useDataStatus();

  if (isLoading) {
    return <span className="text-sm text-muted-foreground">Loading data status…</span>;
  }
  if (!data) {
    return <span className="text-sm text-muted-foreground">Data status unavailable</span>;
  }

  const updates = Object.values(data)
    .map((s) => s.last_updated)
    .filter((v): v is string => v !== null);
  const oldest = updates.length ? updates.reduce((a, b) => (a < b ? a : b)) : null;
  const level = freshnessLevel(oldest);

  const colorClass = {
    fresh: "text-green-600",
    stale: "text-yellow-600",
    old: "text-red-600",
    unknown: "text-muted-foreground",
  }[level];

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className={cn("text-sm cursor-help", colorClass)}>
            Data updated {relativeTime(oldest)}
          </span>
        </TooltipTrigger>
        <TooltipContent>
          <div className="space-y-1 text-xs">
            {Object.entries(data).map(([source, status]) => (
              <div key={source} className="flex gap-3">
                <span className="font-semibold w-24">{source}</span>
                <span>
                  {status.last_error
                    ? `error: ${status.last_error.slice(0, 60)}`
                    : relativeTime(status.last_updated)}
                </span>
              </div>
            ))}
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
```

- [ ] **Step 4: Create `web/src/components/GenerateButton.tsx`**

```tsx
import { Button } from "@/components/ui/button";
import { Loader2 } from "lucide-react";

interface GenerateButtonProps {
  disabled: boolean;
  isPending: boolean;
  onClick: () => void;
}

export function GenerateButton({ disabled, isPending, onClick }: GenerateButtonProps) {
  return (
    <Button onClick={onClick} disabled={disabled || isPending} size="lg">
      {isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
      Generate
    </Button>
  );
}
```

- [ ] **Step 5: Create `web/src/components/Header.tsx`**

```tsx
import { DataFreshness } from "./DataFreshness";
import { GenerateButton } from "./GenerateButton";

interface HeaderProps {
  generateDisabled: boolean;
  generateIsPending: boolean;
  onGenerate: () => void;
}

export function Header({ generateDisabled, generateIsPending, onGenerate }: HeaderProps) {
  return (
    <header className="flex items-center justify-between border-b bg-card px-6 py-4">
      <div className="flex items-baseline gap-6">
        <h1 className="text-2xl font-bold text-foreground">AutoTiers</h1>
        <DataFreshness />
      </div>
      <GenerateButton
        disabled={generateDisabled}
        isPending={generateIsPending}
        onClick={onGenerate}
      />
    </header>
  );
}
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
npm test
```

Expected: DataFreshness tests pass.

- [ ] **Step 7: Commit**

```bash
cd /Users/karlkell/Code/AutoTiers && git add web/src/components/Header.tsx web/src/components/DataFreshness.tsx web/src/components/GenerateButton.tsx web/src/tests/components/DataFreshness.test.tsx && git commit -m "feat(web): Header with DataFreshness indicator and GenerateButton"
```

---

## Task 9: ScoreWeights component (3 linked sliders)

**Files:**
- Create: `web/src/components/ScoreWeights.tsx`
- Create: `web/src/tests/components/ScoreWeights.test.tsx`

- [ ] **Step 1: Write failing tests**

Create `web/src/tests/components/ScoreWeights.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ScoreWeights } from "@/components/ScoreWeights";
import type { Weights } from "@/lib/weights";

describe("ScoreWeights", () => {
  it("renders all three weight values as percentages", () => {
    const weights: Weights = { prior: 40, espn: 30, consensus: 30 };
    render(<ScoreWeights weights={weights} onChange={() => {}} />);
    expect(screen.getByText("40%")).toBeInTheDocument();
    // espn and consensus both 30
    expect(screen.getAllByText("30%")).toHaveLength(2);
  });

  it("shows the sum and a 'sums 100%' indicator", () => {
    const weights: Weights = { prior: 40, espn: 30, consensus: 30 };
    render(<ScoreWeights weights={weights} onChange={() => {}} />);
    expect(screen.getByText(/sums.*100/i)).toBeInTheDocument();
  });

  it("calls onChange with redistributed weights when a slider is adjusted", async () => {
    const onChange = vi.fn();
    const weights: Weights = { prior: 40, espn: 30, consensus: 30 };
    render(<ScoreWeights weights={weights} onChange={onChange} />);

    // Radix sliders accept keyboard input — focus and press ArrowRight 10 times = +10
    const sliders = screen.getAllByRole("slider");
    sliders[0].focus();
    const user = userEvent.setup();
    await user.keyboard("{ArrowRight>10}");

    expect(onChange).toHaveBeenCalled();
    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    expect(lastCall.prior + lastCall.espn + lastCall.consensus).toBe(100);
  });
});
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npm test
```

Expected: FAIL — `@/components/ScoreWeights` doesn't exist.

- [ ] **Step 3: Create `web/src/components/ScoreWeights.tsx`**

```tsx
import { Slider } from "@/components/ui/slider";
import { Label } from "@/components/ui/label";
import { redistribute, weightsAreValid, type Weights, type WeightKey } from "@/lib/weights";
import { cn } from "@/lib/utils";

interface ScoreWeightsProps {
  weights: Weights;
  onChange: (next: Weights) => void;
}

const ROWS: { key: WeightKey; label: string }[] = [
  { key: "prior", label: "Prior year actuals" },
  { key: "espn", label: "ESPN projection" },
  { key: "consensus", label: "FantasyPros consensus" },
];

export function ScoreWeights({ weights, onChange }: ScoreWeightsProps) {
  const valid = weightsAreValid(weights);

  return (
    <div className="space-y-3">
      <Label>Score weights</Label>
      {ROWS.map(({ key, label }) => (
        <div key={key} className="space-y-1">
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>{label}</span>
            <span className="font-mono">{weights[key]}%</span>
          </div>
          <Slider
            value={[weights[key]]}
            min={0}
            max={100}
            step={1}
            onValueChange={([v]) => onChange(redistribute(key, v, weights))}
            aria-label={label}
          />
        </div>
      ))}
      <div className={cn("text-xs", valid ? "text-green-600" : "text-red-600")}>
        {valid ? "✓ Sums 100%" : `✗ Sums ${weights.prior + weights.espn + weights.consensus}% (must be 100%)`}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests**

```bash
npm test
```

Expected: ScoreWeights tests pass.

- [ ] **Step 5: Commit**

```bash
cd /Users/karlkell/Code/AutoTiers && git add web/src/components/ScoreWeights.tsx web/src/tests/components/ScoreWeights.test.tsx && git commit -m "feat(web): ScoreWeights component with linked sliders"
```

---

## Task 10: SettingsPanel

**Files:**
- Create: `web/src/components/SettingsPanel.tsx`

- [ ] **Step 1: Create the component**

Create `web/src/components/SettingsPanel.tsx`:

```tsx
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ScoreWeights } from "./ScoreWeights";
import type { ScoringFormat, LeagueType, LeagueSize, QbTdPoints } from "@/api/types";
import type { Weights } from "@/lib/weights";

export interface SettingsState {
  scoring_format: ScoringFormat;
  league_type: LeagueType;
  league_size: LeagueSize;
  qb_td_points: QbTdPoints;
  bonus_100yd_rushing: boolean;
  bonus_100yd_receiving: boolean;
  bonus_first_downs: boolean;
  weights: Weights;
}

interface SettingsPanelProps {
  value: SettingsState;
  onChange: (next: SettingsState) => void;
}

const LEAGUE_SIZES: LeagueSize[] = [8, 10, 12, 14, 16];

export function SettingsPanel({ value, onChange }: SettingsPanelProps) {
  const set = <K extends keyof SettingsState>(key: K, v: SettingsState[K]) =>
    onChange({ ...value, [key]: v });

  return (
    <aside className="space-y-6 border-r bg-card p-6 overflow-y-auto">
      <h2 className="text-lg font-semibold">Settings</h2>

      <div className="space-y-2">
        <Label>League type</Label>
        <RadioGroup
          value={value.league_type}
          onValueChange={(v) => set("league_type", v as LeagueType)}
        >
          {(["standard", "dynasty", "keeper"] as const).map((opt) => (
            <div key={opt} className="flex items-center gap-2">
              <RadioGroupItem value={opt} id={`lt-${opt}`} />
              <Label htmlFor={`lt-${opt}`} className="capitalize cursor-pointer">{opt}</Label>
            </div>
          ))}
        </RadioGroup>
      </div>

      <div className="space-y-2">
        <Label>Scoring format</Label>
        <RadioGroup
          value={value.scoring_format}
          onValueChange={(v) => set("scoring_format", v as ScoringFormat)}
        >
          {([
            ["standard", "Standard"],
            ["half_ppr", "Half PPR"],
            ["ppr", "Full PPR"],
            ["te_premium", "TE Premium"],
          ] as const).map(([val, label]) => (
            <div key={val} className="flex items-center gap-2">
              <RadioGroupItem value={val} id={`sf-${val}`} />
              <Label htmlFor={`sf-${val}`} className="cursor-pointer">{label}</Label>
            </div>
          ))}
        </RadioGroup>
      </div>

      <div className="space-y-2">
        <Label>League size</Label>
        <Select
          value={String(value.league_size)}
          onValueChange={(v) => set("league_size", Number(v) as LeagueSize)}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {LEAGUE_SIZES.map((n) => (
              <SelectItem key={n} value={String(n)}>{n} teams</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <Label>QB passing TDs</Label>
        <RadioGroup
          value={String(value.qb_td_points)}
          onValueChange={(v) => set("qb_td_points", Number(v) as QbTdPoints)}
          className="flex gap-4"
        >
          {([4, 6] as const).map((n) => (
            <div key={n} className="flex items-center gap-2">
              <RadioGroupItem value={String(n)} id={`qb-${n}`} />
              <Label htmlFor={`qb-${n}`} className="cursor-pointer">{n} pts</Label>
            </div>
          ))}
        </RadioGroup>
      </div>

      <div className="space-y-3">
        <Label>Bonuses</Label>
        {([
          ["bonus_100yd_rushing", "100-yd rushing"],
          ["bonus_100yd_receiving", "100-yd receiving"],
          ["bonus_first_downs", "First down bonus"],
        ] as const).map(([key, label]) => (
          <div key={key} className="flex items-center justify-between">
            <Label htmlFor={key} className="cursor-pointer">{label}</Label>
            <Switch
              id={key}
              checked={value[key]}
              onCheckedChange={(v) => set(key, v)}
            />
          </div>
        ))}
      </div>

      <ScoreWeights
        weights={value.weights}
        onChange={(w) => set("weights", w)}
      />
    </aside>
  );
}
```

- [ ] **Step 2: Verify it typechecks**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd /Users/karlkell/Code/AutoTiers && git add web/src/components/SettingsPanel.tsx && git commit -m "feat(web): SettingsPanel composing all league configuration widgets"
```

---

## Task 11: RuleItem + RuleCategory + RulesPanel

**Files:**
- Create: `web/src/components/RuleItem.tsx`
- Create: `web/src/components/RuleCategory.tsx`
- Create: `web/src/components/RulesPanel.tsx`
- Create: `web/src/tests/components/RuleItem.test.tsx`

- [ ] **Step 1: Write failing tests for RuleItem**

Create `web/src/tests/components/RuleItem.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RuleItem } from "@/components/RuleItem";
import type { Rule } from "@/api/types";

const baseRule: Rule = {
  name: "Test Rule",
  conditions: [{ field: "age", operator: ">", value: 30 }],
  effect: { type: "multiplier", value: 0.9 },
  enabled: true,
  weight: 1.0,
  is_builtin: true,
  category: "Age/Longevity",
};

describe("RuleItem", () => {
  it("renders the rule name", () => {
    render(<RuleItem rule={baseRule} onChange={() => {}} />);
    expect(screen.getByText("Test Rule")).toBeInTheDocument();
  });

  it("calls onChange when toggle is clicked", async () => {
    const onChange = vi.fn();
    render(<RuleItem rule={baseRule} onChange={onChange} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("switch"));

    expect(onChange).toHaveBeenCalledWith({ ...baseRule, enabled: false });
  });

  it("calls onChange when weight chip is changed", async () => {
    const onChange = vi.fn();
    render(<RuleItem rule={baseRule} onChange={onChange} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("radio", { name: /high/i }));

    expect(onChange).toHaveBeenCalledWith({ ...baseRule, weight: 2.0 });
  });
});
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npm test
```

Expected: FAIL.

- [ ] **Step 3: Create `web/src/components/RuleItem.tsx`**

```tsx
import { Switch } from "@/components/ui/switch";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { Rule } from "@/api/types";

interface RuleItemProps {
  rule: Rule;
  onChange: (next: Rule) => void;
}

const WEIGHT_VALUES = ["0.5", "1.0", "2.0"] as const;
const WEIGHT_LABELS: Record<(typeof WEIGHT_VALUES)[number], string> = {
  "0.5": "low",
  "1.0": "default",
  "2.0": "high",
};

export function RuleItem({ rule, onChange }: RuleItemProps) {
  return (
    <div className="flex items-center justify-between gap-2 py-1">
      <div className="flex items-center gap-2 flex-1 min-w-0">
        <Switch
          checked={rule.enabled}
          onCheckedChange={(v) => onChange({ ...rule, enabled: v })}
        />
        <span className="text-sm truncate">{rule.name}</span>
      </div>
      <ToggleGroup
        type="single"
        value={rule.weight.toFixed(1)}
        onValueChange={(v) => {
          if (v) onChange({ ...rule, weight: Number(v) });
        }}
        disabled={!rule.enabled}
      >
        {WEIGHT_VALUES.map((w) => (
          <ToggleGroupItem key={w} value={w} aria-label={WEIGHT_LABELS[w]}>
            {WEIGHT_LABELS[w]}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
    </div>
  );
}
```

- [ ] **Step 4: Create `web/src/components/RuleCategory.tsx`**

```tsx
import { ChevronDown } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { RuleItem } from "./RuleItem";
import type { Rule } from "@/api/types";

interface RuleCategoryProps {
  name: string;
  rules: Rule[];
  onChangeRule: (next: Rule) => void;
}

export function RuleCategory({ name, rules, onChangeRule }: RuleCategoryProps) {
  return (
    <Collapsible defaultOpen className="border rounded-md">
      <CollapsibleTrigger className="flex w-full items-center justify-between px-3 py-2 text-sm font-medium hover:bg-muted">
        <span>{name}</span>
        <ChevronDown className="h-4 w-4" />
      </CollapsibleTrigger>
      <CollapsibleContent className="px-3 pb-2 space-y-1">
        {rules.map((r) => (
          <RuleItem key={r.name} rule={r} onChange={onChangeRule} />
        ))}
      </CollapsibleContent>
    </Collapsible>
  );
}
```

- [ ] **Step 5: Create `web/src/components/RulesPanel.tsx`**

```tsx
import { useMemo } from "react";
import { RuleCategory } from "./RuleCategory";
import { CustomRulesEditor } from "./CustomRulesEditor";
import { useRules } from "@/api/hooks";
import type { Rule } from "@/api/types";

interface RulesPanelProps {
  rules: Rule[];
  onChange: (next: Rule[]) => void;
}

export function RulesPanel({ rules, onChange }: RulesPanelProps) {
  const { data: builtinRules, isLoading } = useRules();

  // On first render of fetched rules, seed the parent's state if it's empty.
  // This is handled by App.tsx; here we just display whatever's in `rules`.

  const grouped = useMemo(() => {
    const m = new Map<string, Rule[]>();
    for (const r of rules) {
      const cat = r.category || (r.is_builtin ? "Other" : "Custom");
      if (!m.has(cat)) m.set(cat, []);
      m.get(cat)!.push(r);
    }
    return [...m.entries()];
  }, [rules]);

  const updateRule = (updated: Rule) =>
    onChange(rules.map((r) => (r.name === updated.name ? updated : r)));

  const addCustomRule = (rule: Rule) => onChange([...rules, rule]);

  const removeCustomRule = (name: string) =>
    onChange(rules.filter((r) => r.name !== name));

  if (isLoading && !builtinRules) {
    return <aside className="p-6 border-r"><span className="text-sm text-muted-foreground">Loading rules…</span></aside>;
  }

  return (
    <aside className="space-y-3 border-r bg-card p-6 overflow-y-auto">
      <h2 className="text-lg font-semibold">Rules</h2>
      {grouped.map(([cat, rs]) => (
        <RuleCategory key={cat} name={cat} rules={rs} onChangeRule={updateRule} />
      ))}
      <CustomRulesEditor
        existingNames={new Set(rules.map((r) => r.name))}
        onAdd={addCustomRule}
        onRemove={removeCustomRule}
        customRules={rules.filter((r) => !r.is_builtin)}
      />
    </aside>
  );
}
```

- [ ] **Step 6: Run tests**

```bash
npm test
```

Expected: RuleItem tests pass. (RulesPanel + RuleCategory render but aren't tested directly — covered by App integration test in Task 14.)

- [ ] **Step 7: Commit**

```bash
cd /Users/karlkell/Code/AutoTiers && git add web/src/components/RuleItem.tsx web/src/components/RuleCategory.tsx web/src/components/RulesPanel.tsx web/src/tests/components/RuleItem.test.tsx && git commit -m "feat(web): RuleItem/Category/Panel with toggle and weight chip"
```

---

## Task 12: CustomRulesEditor

**Files:**
- Create: `web/src/components/CustomRulesEditor.tsx`
- Create: `web/src/tests/components/CustomRulesEditor.test.tsx`

- [ ] **Step 1: Write failing tests**

Create `web/src/tests/components/CustomRulesEditor.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CustomRulesEditor } from "@/components/CustomRulesEditor";

describe("CustomRulesEditor", () => {
  it("shows valid JSON indicator when input parses", async () => {
    render(<CustomRulesEditor existingNames={new Set()} onAdd={() => {}} onRemove={() => {}} customRules={[]} />);
    const user = userEvent.setup();
    const textarea = screen.getByRole("textbox");
    const validRule = JSON.stringify({
      name: "My Rule",
      conditions: [{ field: "age", operator: ">", value: 30 }],
      effect: { type: "multiplier", value: 0.9 },
    });
    await user.click(textarea);
    await user.paste(validRule);
    expect(await screen.findByText(/valid/i)).toBeInTheDocument();
  });

  it("shows error when JSON is invalid", async () => {
    render(<CustomRulesEditor existingNames={new Set()} onAdd={() => {}} onRemove={() => {}} customRules={[]} />);
    const user = userEvent.setup();
    const textarea = screen.getByRole("textbox");
    await user.click(textarea);
    await user.paste("{not valid json");
    expect(await screen.findByText(/invalid json/i)).toBeInTheDocument();
  });

  it("calls onAdd when 'Add rule' is clicked with valid input", async () => {
    const onAdd = vi.fn();
    render(<CustomRulesEditor existingNames={new Set()} onAdd={onAdd} onRemove={() => {}} customRules={[]} />);
    const user = userEvent.setup();
    const textarea = screen.getByRole("textbox");
    await user.click(textarea);
    await user.paste(JSON.stringify({
      name: "Old Veteran Penalty",
      conditions: [{ field: "age", operator: ">", value: 34 }],
      effect: { type: "multiplier", value: 0.8 },
    }));
    await screen.findByText(/valid/i);
    await user.click(screen.getByRole("button", { name: /add rule/i }));
    expect(onAdd).toHaveBeenCalled();
    const added = onAdd.mock.calls[0][0];
    expect(added.name).toBe("Old Veteran Penalty");
    expect(added.is_builtin).toBe(false);
    expect(added.enabled).toBe(true);
    expect(added.weight).toBe(1.0);
  });

  it("renders custom rules with delete buttons", async () => {
    const onRemove = vi.fn();
    render(
      <CustomRulesEditor
        existingNames={new Set(["My Custom"])}
        onAdd={() => {}}
        onRemove={onRemove}
        customRules={[
          {
            name: "My Custom",
            conditions: [{ field: "age", operator: ">", value: 30 }],
            effect: { type: "multiplier", value: 0.9 },
            enabled: true, weight: 1.0, is_builtin: false, category: "Custom",
          },
        ]}
      />,
    );
    expect(screen.getByText("My Custom")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /remove my custom/i }));
    expect(onRemove).toHaveBeenCalledWith("My Custom");
  });
});
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npm test
```

Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Create `web/src/components/CustomRulesEditor.tsx`**

```tsx
import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { X } from "lucide-react";
import type { Rule, RuleCondition, RuleEffect } from "@/api/types";

interface CustomRulesEditorProps {
  existingNames: Set<string>;
  customRules: Rule[];
  onAdd: (rule: Rule) => void;
  onRemove: (name: string) => void;
}

interface ParseResult {
  ok: boolean;
  rule?: Rule;
  error?: string;
}

function parseRule(input: string, existingNames: Set<string>): ParseResult {
  if (!input.trim()) return { ok: false, error: "" };
  let parsed: unknown;
  try {
    parsed = JSON.parse(input);
  } catch (e) {
    return { ok: false, error: `Invalid JSON: ${(e as Error).message}` };
  }
  if (!parsed || typeof parsed !== "object") return { ok: false, error: "Must be a JSON object" };
  const p = parsed as Partial<Rule>;
  if (typeof p.name !== "string" || !p.name) return { ok: false, error: "Missing 'name' (string)" };
  if (existingNames.has(p.name)) return { ok: false, error: `Rule '${p.name}' already exists` };
  if (!Array.isArray(p.conditions) || p.conditions.length === 0) {
    return { ok: false, error: "Missing 'conditions' (non-empty array)" };
  }
  if (!p.effect || typeof p.effect !== "object") return { ok: false, error: "Missing 'effect' (object)" };
  return {
    ok: true,
    rule: {
      name: p.name,
      conditions: p.conditions as RuleCondition[],
      effect: p.effect as RuleEffect,
      enabled: true,
      weight: 1.0,
      is_builtin: false,
      category: "Custom",
    },
  };
}

export function CustomRulesEditor({
  existingNames,
  customRules,
  onAdd,
  onRemove,
}: CustomRulesEditorProps) {
  const [input, setInput] = useState("");
  const [result, setResult] = useState<ParseResult>({ ok: false });

  useEffect(() => {
    const t = setTimeout(() => setResult(parseRule(input, existingNames)), 300);
    return () => clearTimeout(t);
  }, [input, existingNames]);

  return (
    <div className="border rounded-md p-3 space-y-2">
      <h3 className="text-sm font-medium">Custom rules</h3>
      {customRules.length > 0 && (
        <ul className="space-y-1">
          {customRules.map((r) => (
            <li key={r.name} className="flex items-center justify-between text-sm">
              <span className="truncate">{r.name}</span>
              <Button
                variant="ghost"
                size="sm"
                aria-label={`remove ${r.name}`}
                onClick={() => onRemove(r.name)}
              >
                <X className="h-3 w-3" />
              </Button>
            </li>
          ))}
        </ul>
      )}
      <textarea
        className="w-full h-32 rounded-md border border-input bg-background p-2 text-xs font-mono"
        placeholder='{"name": "My Rule", "conditions": [...], "effect": {...}}'
        value={input}
        onChange={(e) => setInput(e.target.value)}
      />
      {input && (
        result.ok ? (
          <p className="text-xs text-green-600">✓ Valid</p>
        ) : result.error ? (
          <p className="text-xs text-red-600">{result.error}</p>
        ) : null
      )}
      <Button
        size="sm"
        disabled={!result.ok}
        onClick={() => {
          if (result.rule) {
            onAdd(result.rule);
            setInput("");
            setResult({ ok: false });
          }
        }}
      >
        Add rule
      </Button>
    </div>
  );
}
```

- [ ] **Step 4: Run tests**

```bash
npm test
```

Expected: all CustomRulesEditor tests pass.

- [ ] **Step 5: Commit**

```bash
cd /Users/karlkell/Code/AutoTiers && git add web/src/components/CustomRulesEditor.tsx web/src/tests/components/CustomRulesEditor.test.tsx && git commit -m "feat(web): CustomRulesEditor with debounced JSON validation"
```

---

## Task 13: TiersPanel (PositionFilter + TierGroup + PlayerRow + TiersPanel)

**Files:**
- Create: `web/src/components/PositionFilter.tsx`
- Create: `web/src/components/PlayerRow.tsx`
- Create: `web/src/components/TierGroup.tsx`
- Create: `web/src/components/TiersPanel.tsx`
- Create: `web/src/tests/components/TiersPanel.test.tsx`

- [ ] **Step 1: Write failing tests for TiersPanel**

Create `web/src/tests/components/TiersPanel.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TiersPanel } from "@/components/TiersPanel";
import generateResponse from "../fixtures/generate-response.json";
import type { GenerateResponse } from "@/api/types";

const response = generateResponse as GenerateResponse;

describe("TiersPanel", () => {
  it("shows placeholder when no result", () => {
    render(<TiersPanel result={null} isPending={false} onDownloadCsv={() => {}} />);
    expect(screen.getByText(/click generate/i)).toBeInTheDocument();
  });

  it("shows skeleton when pending", () => {
    render(<TiersPanel result={null} isPending={true} onDownloadCsv={() => {}} />);
    expect(screen.getByText(/generating/i)).toBeInTheDocument();
  });

  it("renders all players grouped by tier", () => {
    render(<TiersPanel result={response} isPending={false} onDownloadCsv={() => {}} />);
    expect(screen.getByText("Ja'Marr Chase")).toBeInTheDocument();
    expect(screen.getByText("Bijan Robinson")).toBeInTheDocument();
    expect(screen.getByText("Josh Allen")).toBeInTheDocument();
  });

  it("renders tier headers", () => {
    render(<TiersPanel result={response} isPending={false} onDownloadCsv={() => {}} />);
    expect(screen.getByText(/tier 1/i)).toBeInTheDocument();
    expect(screen.getByText(/tier 2/i)).toBeInTheDocument();
  });

  it("filters by position when a position chip is clicked", async () => {
    render(<TiersPanel result={response} isPending={false} onDownloadCsv={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^wr$/i }));
    expect(screen.getByText("Ja'Marr Chase")).toBeInTheDocument();
    expect(screen.getByText("Justin Jefferson")).toBeInTheDocument();
    expect(screen.queryByText("Bijan Robinson")).not.toBeInTheDocument();
    expect(screen.queryByText("Josh Allen")).not.toBeInTheDocument();
  });

  it("calls onDownloadCsv when CSV button clicked", async () => {
    const onDownload = vi.fn();
    render(<TiersPanel result={response} isPending={false} onDownloadCsv={onDownload} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /download csv/i }));
    expect(onDownload).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npm test
```

Expected: FAIL.

- [ ] **Step 3: Create `web/src/components/PositionFilter.tsx`**

```tsx
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type PositionFilterValue = "ALL" | "QB" | "RB" | "WR" | "TE" | "K" | "DST";

const OPTIONS: PositionFilterValue[] = ["ALL", "QB", "RB", "WR", "TE", "K", "DST"];

interface PositionFilterProps {
  value: PositionFilterValue;
  onChange: (next: PositionFilterValue) => void;
}

export function PositionFilter({ value, onChange }: PositionFilterProps) {
  return (
    <div className="flex flex-wrap gap-1">
      {OPTIONS.map((opt) => (
        <Button
          key={opt}
          variant={value === opt ? "default" : "outline"}
          size="sm"
          onClick={() => onChange(opt)}
          className={cn(value === opt && "pointer-events-none")}
        >
          {opt === "ALL" ? "All" : opt}
        </Button>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Create `web/src/components/PlayerRow.tsx`**

```tsx
import type { TieredPlayer } from "@/api/types";

interface PlayerRowProps {
  player: TieredPlayer;
}

export function PlayerRow({ player }: PlayerRowProps) {
  return (
    <div className="flex items-center gap-3 px-3 py-2 hover:bg-muted/50 rounded-md text-sm">
      <span className="w-8 text-right font-mono text-muted-foreground">{player.overall_rank}</span>
      <span className="flex-1 truncate font-medium">{player.name}</span>
      <span className="w-16 text-xs text-muted-foreground">{player.positional_tier}</span>
      <span className="w-12 text-xs text-muted-foreground">{player.team ?? "—"}</span>
      <span className="w-10 text-right font-mono">{player.adjusted_score.toFixed(1)}</span>
      {player.flags.length > 0 && (
        <span className="flex flex-wrap gap-1">
          {player.flags.map((f) => (
            <span key={f} className="rounded bg-yellow-100 text-yellow-800 px-1.5 py-0.5 text-xs">
              {f}
            </span>
          ))}
        </span>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Create `web/src/components/TierGroup.tsx`**

```tsx
import { PlayerRow } from "./PlayerRow";
import type { TieredPlayer } from "@/api/types";

interface TierGroupProps {
  tier: number;
  players: TieredPlayer[];
}

export function TierGroup({ tier, players }: TierGroupProps) {
  return (
    <div className="space-y-1">
      <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground py-1">
        ── Tier {tier} ──
      </div>
      {players.map((p) => (
        <PlayerRow key={p.player_id} player={p} />
      ))}
    </div>
  );
}
```

- [ ] **Step 6: Create `web/src/components/TiersPanel.tsx`**

```tsx
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Download } from "lucide-react";
import { PositionFilter, type PositionFilterValue } from "./PositionFilter";
import { TierGroup } from "./TierGroup";
import type { GenerateResponse } from "@/api/types";

interface TiersPanelProps {
  result: GenerateResponse | null;
  isPending: boolean;
  onDownloadCsv: () => void;
}

export function TiersPanel({ result, isPending, onDownloadCsv }: TiersPanelProps) {
  const [filter, setFilter] = useState<PositionFilterValue>("ALL");

  const groupedByTier = useMemo(() => {
    if (!result) return [];
    const filtered = filter === "ALL"
      ? result.players
      : result.players.filter((p) => p.position === filter);
    const m = new Map<number, typeof filtered>();
    for (const p of filtered) {
      if (!m.has(p.overall_tier)) m.set(p.overall_tier, []);
      m.get(p.overall_tier)!.push(p);
    }
    return [...m.entries()].sort(([a], [b]) => a - b);
  }, [result, filter]);

  if (isPending) {
    return (
      <section className="p-6 overflow-y-auto">
        <h2 className="text-lg font-semibold mb-3">Tiers</h2>
        <p className="text-sm text-muted-foreground">Generating tier list…</p>
        <div className="mt-4 space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-8 bg-muted rounded-md animate-pulse" />
          ))}
        </div>
      </section>
    );
  }

  if (!result) {
    return (
      <section className="p-6">
        <h2 className="text-lg font-semibold mb-3">Tiers</h2>
        <p className="text-sm text-muted-foreground">
          Click Generate to build your tier list.
        </p>
      </section>
    );
  }

  return (
    <section className="p-6 overflow-y-auto space-y-4">
      <h2 className="text-lg font-semibold">Tiers</h2>
      <PositionFilter value={filter} onChange={setFilter} />
      <div className="space-y-4">
        {groupedByTier.map(([tier, players]) => (
          <TierGroup key={tier} tier={tier} players={players} />
        ))}
      </div>
      <Button onClick={onDownloadCsv} variant="outline" className="w-full">
        <Download className="mr-2 h-4 w-4" />
        Download CSV
      </Button>
    </section>
  );
}
```

- [ ] **Step 7: Run tests**

```bash
npm test
```

Expected: all TiersPanel tests pass.

- [ ] **Step 8: Commit**

```bash
cd /Users/karlkell/Code/AutoTiers && git add web/src/components/PositionFilter.tsx web/src/components/PlayerRow.tsx web/src/components/TierGroup.tsx web/src/components/TiersPanel.tsx web/src/tests/components/TiersPanel.test.tsx && git commit -m "feat(web): TiersPanel with position filter and tier groups"
```

---

## Task 14: App.tsx wire-up + integration test

**Files:**
- Modify: `web/src/App.tsx`
- Create: `web/src/tests/App.test.tsx`

- [ ] **Step 1: Write the integration test (happy path)**

Create `web/src/tests/App.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "@/App";

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><App /></QueryClientProvider>);
}

describe("App (integration)", () => {
  it("loads, allows generating, and shows tier results", async () => {
    renderApp();

    // Header renders
    expect(screen.getByText("AutoTiers")).toBeInTheDocument();

    // Rules load from MSW
    await waitFor(() => {
      expect(screen.getByText("Target Share Premium")).toBeInTheDocument();
    });

    // Settings panel renders
    expect(screen.getByText(/league type/i)).toBeInTheDocument();
    expect(screen.getByText(/score weights/i)).toBeInTheDocument();

    // Generate button is enabled (default weights sum to 100)
    const generateButton = screen.getByRole("button", { name: /^generate$/i });
    expect(generateButton).not.toBeDisabled();

    // Click Generate
    const user = userEvent.setup();
    await user.click(generateButton);

    // Tier results render
    await waitFor(() => {
      expect(screen.getByText("Ja'Marr Chase")).toBeInTheDocument();
    });
    expect(screen.getByText("Bijan Robinson")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npm test
```

Expected: FAIL — App.tsx is still the placeholder.

- [ ] **Step 3: Rewrite `web/src/App.tsx` with the full layout**

```tsx
import { useEffect, useState } from "react";
import { Header } from "@/components/Header";
import { SettingsPanel, type SettingsState } from "@/components/SettingsPanel";
import { RulesPanel } from "@/components/RulesPanel";
import { TiersPanel } from "@/components/TiersPanel";
import { useRules, useGenerateMutation, downloadCsv } from "@/api/hooks";
import { weightsAreValid } from "@/lib/weights";
import type { Rule, GenerateRequest } from "@/api/types";

const DEFAULT_SETTINGS: SettingsState = {
  scoring_format: "ppr",
  league_type: "standard",
  league_size: 12,
  qb_td_points: 4,
  bonus_100yd_rushing: false,
  bonus_100yd_receiving: false,
  bonus_first_downs: false,
  weights: { prior: 40, espn: 30, consensus: 30 },
};

export default function App() {
  const [settings, setSettings] = useState<SettingsState>(DEFAULT_SETTINGS);
  const [rules, setRules] = useState<Rule[]>([]);
  const { data: fetchedRules } = useRules();
  const generate = useGenerateMutation();

  // Seed local rules state once the backend response arrives.
  useEffect(() => {
    if (fetchedRules && rules.length === 0) {
      setRules(fetchedRules);
    }
  }, [fetchedRules, rules.length]);

  const buildRequest = (): GenerateRequest => ({
    scoring_format: settings.scoring_format,
    league_type: settings.league_type,
    league_size: settings.league_size,
    qb_td_points: settings.qb_td_points,
    bonus_100yd_rushing: settings.bonus_100yd_rushing,
    bonus_100yd_receiving: settings.bonus_100yd_receiving,
    bonus_first_downs: settings.bonus_first_downs,
    weight_prior_year: settings.weights.prior / 100,
    weight_espn: settings.weights.espn / 100,
    weight_consensus: settings.weights.consensus / 100,
    rules,
  });

  const canGenerate = weightsAreValid(settings.weights) && rules.length > 0;

  return (
    <div className="flex flex-col h-screen">
      <Header
        generateDisabled={!canGenerate}
        generateIsPending={generate.isPending}
        onGenerate={() => generate.mutate(buildRequest())}
      />
      <main className="flex-1 grid grid-cols-1 lg:grid-cols-[300px_minmax(0,1fr)_minmax(0,1.5fr)] overflow-hidden">
        <SettingsPanel value={settings} onChange={setSettings} />
        <RulesPanel rules={rules} onChange={setRules} />
        <TiersPanel
          result={generate.data ?? null}
          isPending={generate.isPending}
          onDownloadCsv={() => downloadCsv(buildRequest())}
        />
      </main>
    </div>
  );
}
```

- [ ] **Step 4: Run tests**

```bash
npm test
```

Expected: all tests pass, including the new App integration test.

- [ ] **Step 5: Open in browser and click around**

Make sure the dev container is running (`podman compose up`). Open http://localhost:5173. Should see:
- Three-panel layout (Settings | Rules | Tiers)
- Settings populated with defaults
- Rules from `/api/rules` populated (you need the backend running with `podman compose up` for this)
- Click Generate → tier list appears in the right panel
- Click "Download CSV" → file saves

(Skip this step if Docker isn't available; the test suite covers the behavior.)

- [ ] **Step 6: Commit**

```bash
cd /Users/karlkell/Code/AutoTiers && git add web/src/App.tsx web/src/tests/App.test.tsx && git commit -m "feat(web): wire App.tsx + happy-path integration test"
```

---

## Task 15: README update + open PR

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a Frontend section to the README**

Find the existing "Run with Docker or Podman" section. After it, before the "Backend — Local Setup (without Docker)" section, insert a new "Frontend" section:

```markdown
## Frontend

The React frontend lives in `web/`. With docker-compose, it comes up automatically alongside the backend at http://localhost:5173.

To run the frontend without Docker (against a containerized backend):

```bash
cd web
npm install
npm run dev
# → opens http://localhost:5173
```

The frontend reads `VITE_API_URL` from its environment. In Docker it's set to `http://localhost:8000`; for host-side dev override via `web/.env.local`:

```
VITE_API_URL=http://localhost:8000
```

### Frontend tests

```bash
cd web
npm test            # one-shot
npm run test:watch  # watch mode
```
```

Read the existing README first to find the exact insertion point. Don't disturb the existing sections.

- [ ] **Step 2: Run the full suite one final time**

```bash
cd /Users/karlkell/Code/AutoTiers/web && npm test 2>&1 | tail -10
```

Expected: all tests pass (roughly 25+ tests total).

- [ ] **Step 3: Commit**

```bash
cd /Users/karlkell/Code/AutoTiers && git add README.md && git commit -m "docs: add frontend section to README"
```

- [ ] **Step 4: Push branch + open PR**

```bash
git push -u origin frontend
gh pr create --title "feat: AutoTiers React frontend (Plan 3)" --body "$(cat <<'EOF'
## Summary

Three-panel React app (Settings / Rules / Tiers) that calls the existing FastAPI backend. Closes the v1 loop: anonymous users can land on the page, configure a draft, and download a CSV of ranked players in tiers.

**Stack:** React 18 + TypeScript + Vite + TanStack Query v5 + Tailwind + shadcn/ui (Radix primitives). Vitest + Testing Library + MSW for tests.

## What's in

- `web/` directory scaffolded with Vite + TS, Tailwind, and shadcn/ui primitives (Button, Slider, Switch, Select, RadioGroup, ToggleGroup, Label, Collapsible, Tooltip)
- API layer: typed against the backend's Pydantic schemas; TanStack Query hooks (`useRules`, `useDataStatus`, `useGenerateMutation`) + a `downloadCsv` helper
- Linked weight sliders: integer steps, redistribute proportionally, sum stays at 100
- Rule editor: per-rule toggle + 3-position weight chip (low/default/high)
- Custom rules: JSON textarea with debounced inline validation, add/remove
- Tier display: position filter, tier groups, CSV download
- Data freshness indicator in header (color-coded by age, tooltip shows per-source state)
- New `web` service in docker-compose for one-command local dev

## Test plan

- [x] `cd web && npm test` — all unit + integration tests pass
- [x] `npx tsc --noEmit` — no TypeScript errors
- [ ] `podman compose down -v && podman compose up --build` — full stack comes up
- [ ] Open http://localhost:5173 — UI renders with rules loaded
- [ ] Adjust weights, toggle rules, click Generate — tier list renders
- [ ] Filter by position, click Download CSV — file saves correctly

## Deferred

- URL-state hydration (shareable configs) — Plan 4
- Dark mode — easy to add later via Tailwind `dark:` classes
- i18n, SSR, accounts — out of scope per v1 spec

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review Notes

After all tasks complete:

1. **Spec coverage** — every section of `2026-05-21-autotiers-frontend-design.md` maps to a task:
   - Stack + scaffold → Tasks 1, 2
   - Docker integration → Task 3
   - API types/client/hooks → Task 4
   - Test setup → Task 5
   - Linked weights → Task 6
   - Format helpers → Task 7
   - Header + DataFreshness + GenerateButton → Task 8
   - ScoreWeights → Task 9
   - SettingsPanel → Task 10
   - RulesPanel + RuleItem + RuleCategory → Task 11
   - CustomRulesEditor → Task 12
   - TiersPanel + PositionFilter + TierGroup + PlayerRow → Task 13
   - App.tsx wire-up + integration test → Task 14
   - README + PR → Task 15

2. **Responsive behavior** — covered by Tailwind classes in App.tsx (`grid-cols-1 lg:grid-cols-[300px_...]`). Mobile stacks vertically; desktop is three columns.

3. **Operational follow-up** — after merge: Railway picks up the new `web` service; set `VITE_API_URL` in the frontend service env to point at the deployed backend; tighten backend `CORS_ORIGINS` from `["*"]` to the frontend's domain.
