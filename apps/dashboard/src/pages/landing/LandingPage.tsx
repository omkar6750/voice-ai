import { lazy, Suspense } from "react";
import { Show, SignInButton, SignUpButton } from "@clerk/react";
import { useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  AudioLines,
  Braces,
  Check,
  Cpu,
  CalendarDays,
  MessageCircle,
  Phone,
  ScanLine,
  Code2,
  Layers,
  Menu,
  Radio,
  ShieldCheck,
  Terminal,
  Workflow,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { FadeContent } from "@/components/react-bits/Motion";
import { cn } from "@/lib/utils";
import { clerkUrls } from "@/app/clerk-config";

const RunPreview = lazy(() => import("./RunPreview"));
const github = "https://github.com/omkar6750/voice-ai";
const product =
  "https://robu.in/product/waveshare-sim7600g-h-m-2-4g-hat-for-raspberry-pi-lte-cat4-high-speed-4g-3g-2g-gnss-global-band/";
// Scoped semantic tokens leave the operational dashboard palette unchanged.
export const landingTheme = "landing-theme bg-background text-foreground";
const gutter = "mx-auto w-full max-w-6xl px-6 md:px-12";
const eyebrow = "font-mono text-[11px] uppercase tracking-[.2em] text-primary";

export function Brand() {
  return (
    <Link
      to="/"
      aria-label="Voice AI home"
      className="flex items-center gap-2.5 font-medium tracking-tight"
    >
      <AudioLines className="size-6 text-primary" />
      VOICE AI
      <span className="ml-1 font-mono text-[9px] tracking-widest text-muted-foreground">
        / PLATFORM
      </span>
    </Link>
  );
}

function Entry({ large = false }: { large?: boolean }) {
  return (
    <>
      <Show when="signed-in">
        <Button
          asChild
          size={large ? "lg" : "default"}
          className={cn("rounded-none", large && "h-12 px-6")}
        >
          <Link to="/runs">
            Open dashboard
            <ArrowUpRight data-icon="inline-end" />
          </Link>
        </Button>
      </Show>
      <Show when="signed-out">
        <Button
          asChild
          size={large ? "lg" : "default"}
          className={cn("rounded-none", large && "h-12 px-6")}
        >
          <Link to={clerkUrls.signUp}>
            Start building
            <ArrowUpRight data-icon="inline-end" />
          </Link>
        </Button>
      </Show>
    </>
  );
}

function Header() {
  const [menuOpen, setMenuOpen] = useState(false);
  const navigation = [
    { href: "#platform", label: "Platform" },
    { href: "#architecture", label: "Architecture" },
    { href: "#connectivity", label: "Connectivity" },
  ];
  return (
    <header className="absolute inset-x-0 top-0 z-20 border-b border-white/10">
      <div
        className={cn(gutter, "flex h-20 items-center justify-between gap-5")}
      >
        <Brand />
        <nav
          aria-label="Main navigation"
          className="hidden items-center gap-7 text-sm text-white/70 lg:flex"
        >
          {navigation.map((item) => (
            <a
              key={item.href}
              href={item.href}
              className="transition-colors hover:text-primary focus-visible:outline focus-visible:outline-primary"
            >
              {item.label}
            </a>
          ))}
        </nav>
        <div className="flex items-center gap-4">
          <a
            href={github}
            target="_blank"
            rel="noreferrer"
            aria-label="View GitHub repository"
            className="text-muted-foreground transition-colors hover:text-foreground"
          >
            <Code2 className="size-5" />
          </a>
          <Show when="signed-out">
            <SignInButton mode="modal" forceRedirectUrl="/">
              <Button variant="ghost" className="rounded-none">
                Sign in
              </Button>
            </SignInButton>
            <SignUpButton mode="modal" forceRedirectUrl="/">
              <Button className="rounded-none">Sign up</Button>
            </SignUpButton>
          </Show>
          <Show when="signed-in">
            <Button asChild className="rounded-none">
              <Link to="/runs">
                Dashboard
                <ArrowUpRight data-icon="inline-end" />
              </Link>
            </Button>
          </Show>
          <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
            <SheetTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="lg:hidden"
                aria-label="Open navigation"
              >
                <Menu />
              </Button>
            </SheetTrigger>
            <SheetContent
              className={cn(landingTheme, "w-full! max-w-none! border-0")}
            >
              <SheetTitle>Voice AI</SheetTitle>
              <nav
                aria-label="Mobile navigation"
                className="flex flex-1 flex-col justify-center gap-8 text-3xl"
              >
                {navigation.map((item) => (
                  <a
                    key={item.href}
                    href={item.href}
                    onClick={() => setMenuOpen(false)}
                  >
                    {item.label}
                  </a>
                ))}
                <Show when="signed-out">
                  <Link to={clerkUrls.signIn}>Sign in</Link>
                </Show>
                <Entry large />
              </nav>
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </header>
  );
}

const stages = [
  {
    icon: Layers,
    title: "Author",
    tech: "React · Clerk",
    text: "Configure flows, prompts, tools and knowledge. Publish immutable versions within a Clerk Organization.",
  },
  {
    icon: Braces,
    title: "Control",
    tech: "FastAPI · MCP",
    text: "An authenticated API owns configuration and call control. User-bound MCP access applies tenant permissions to reviewed operations.",
  },
  {
    icon: AudioLines,
    title: "Converse",
    tech: "Pipecat · Python",
    text: "A conversation pipeline connects speech recognition, language models, synthesis, flow transitions and tools behind provider adapters.",
  },
  {
    icon: Radio,
    title: "Connect",
    tech: "Twilio · SIM7600",
    text: "Cloud telephony and a Windows-native cellular modem path connect the voice pipeline to calls. Browser and text tests provide development channels.",
  },
  {
    icon: Terminal,
    title: "Inspect",
    tech: "PostgreSQL · pgvector",
    text: "Retain run-linked transcripts, flow visits, tool outcomes and diagnostics. Retrieve knowledge and inspect selected execution evidence.",
  },
];

function Architecture() {
  const [selected, setSelected] = useState(2);
  return (
    <section
      id="architecture"
      className={cn(gutter, "scroll-mt-8 py-24 md:py-32")}
    >
      <FadeContent>
        <p className={eyebrow}>02 / Under the surface</p>
        <div className="mt-5 flex flex-col justify-between gap-6 md:flex-row md:items-end">
          <h2 className="max-w-2xl text-4xl font-medium leading-tight tracking-[-.05em] md:text-6xl">
            A voice interface.
            <br />
            <span className="text-muted-foreground">
              An entire system behind it.
            </span>
          </h2>
          <p className="max-w-xs text-sm leading-6 text-muted-foreground">
            From a versioned prompt to a physical call. Follow each boundary.
          </p>
        </div>
        <div className="mt-14 grid border-y border-border md:grid-cols-5">
          {stages.map(({ icon: Icon, title, tech }, index) => (
            <button
              key={title}
              type="button"
              aria-pressed={selected === index}
              onClick={() => setSelected(index)}
              className={cn(
                "group flex items-center gap-4 border-b border-border p-6 text-left transition-colors focus-visible:outline focus-visible:outline-primary md:flex-col md:items-start md:border-r md:border-b-0 md:last:border-r-0",
                selected === index ? "bg-primary/10" : "hover:bg-card",
              )}
            >
              <Icon
                className={cn(
                  "size-6",
                  selected === index ? "text-primary" : "text-muted-foreground",
                )}
              />
              <div>
                <span className="font-mono text-[10px] text-muted-foreground">
                  0{index + 1}
                </span>
                <h3 className="mt-2 text-xl">{title}</h3>
                <p className="mt-2 font-mono text-[10px] text-muted-foreground">
                  {tech}
                </p>
              </div>
              <ArrowRight className="ml-auto size-4 text-primary md:ml-0" />
            </button>
          ))}
        </div>
        <div
          aria-live="polite"
          className="mt-6 flex min-h-24 flex-col gap-4 md:flex-row md:gap-12"
        >
          <span className="min-w-32 font-mono text-xs text-primary">
            {stages[selected].title.toUpperCase()} /
          </span>
          <p className="max-w-3xl text-sm leading-7 text-muted-foreground">
            {stages[selected].text}
          </p>
        </div>
        <div className="mt-8 flex flex-wrap gap-x-8 gap-y-4 border-t border-border pt-6 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          <span>STT → LLM → TTS</span>
          <span>Provider adapters</span>
          <span>Versioned contracts</span>
          <span>Durable evidence</span>
          <span>Tenant-scoped access</span>
        </div>
      </FadeContent>
    </section>
  );
}

const capabilities = [
  {
    icon: Phone,
    title: "Real voice calling",
    text: "Connect cloud calls through Twilio, test in your browser, or use SIM7600 for local cellular testing.",
    tags: "TWILIO / BROWSER / SIM7600",
  },
  {
    icon: MessageCircle,
    title: "WhatsApp during calls",
    text: "Compose contextual follow-ups from the conversation and inspect message actions alongside the call transcript.",
    tags: "COMPOSE / FOLLOW UP / TRACE",
  },
  {
    icon: CalendarDays,
    title: "Calendar booking",
    text: "Check availability, route to an eligible team member and connect booking actions to the conversation.",
    tags: "AVAILABILITY / SCHEDULING / TOOLS",
  },
  {
    icon: ScanLine,
    title: "Fast lead classification",
    text: "Use JEV AI by TypeSafe AI for fast, structured lead classification. Capture intent and qualify leads inside your agent workflow.",
    tags: "JEV AI / TYPESAFE AI / QUALIFICATION",
  },
  {
    icon: Workflow,
    title: "Your tools via MCP",
    text: "Connect MCP servers and API actions. Give agents the tools and knowledge they need to take useful next steps.",
    tags: "MCP / APIs / KNOWLEDGE",
  },
  {
    icon: ShieldCheck,
    title: "Multi-tenant workspaces",
    text: "Manage organizations, agents and team access with Clerk Organizations, membership checks and encrypted action secrets.",
    tags: "ORGANIZATIONS / ROLES / VAULT",
  },
];
export default function LandingPage() {
  return (
    <div
      className={cn(landingTheme, "overflow-x-clip selection:bg-primary/30")}
    >
      <a
        href="#platform"
        className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-black focus:p-4"
      >
        Skip to platform
      </a>
      <section className="relative isolate flex min-h-svh items-center overflow-hidden bg-black">
        <Header />
        <div className={cn(gutter, "pt-32 pb-28")}>
          <p className={eyebrow}>VOICE AI / NO-CODE AGENT CONFIGURATION</p>
          <h1 className="mt-8 max-w-5xl text-[clamp(3.8rem,9vw,8.5rem)] font-medium leading-[.98] tracking-[-.065em]">
            Call. Qualify. Book.
            <br />
            <span className="text-primary">Automatically.</span>
          </h1>
          <p className="mt-8 max-w-xl text-lg leading-8 text-muted-foreground">
            Build voice agents that turn conversations into action. Connect your
            knowledge, tools and workflows.
          </p>{" "}
          <div className="mt-9 flex flex-wrap items-center gap-5">
            <Entry large />
            <a
              href="#platform"
              className="group flex items-center gap-3 text-sm"
            >
              Explore the platform
              <ArrowDown className="size-4 transition-transform group-hover:translate-y-1 motion-reduce:transform-none" />
            </a>
          </div>
        </div>
        <div
          className={cn(
            gutter,
            "absolute inset-x-0 bottom-7 flex justify-between font-mono text-[10px] uppercase tracking-widest text-muted-foreground",
          )}
        >
          <span>Built by Omkar / Engineering showcase</span>
          <span className="hidden sm:block">Voice → Intelligence → Action</span>
        </div>
      </section>
      <div className="border-y border-border">
        <div
          className={cn(
            gutter,
            "flex flex-wrap items-center justify-between gap-6 py-7 font-mono text-xs text-muted-foreground",
          )}
        >
          <span className="text-foreground">THE STACK /</span>
          {["Pipecat", "FastAPI", "PostgreSQL", "React", "Clerk", "Twilio"].map(
            (item) => (
              <span key={item}>{item}</span>
            ),
          )}
        </div>
      </div>

      <section
        id="platform"
        className={cn(gutter, "scroll-mt-8 py-24 md:py-32")}
      >
        <FadeContent>
          <p className={eyebrow}>01 / The control room</p>
          <div className="mt-5 grid gap-6 md:grid-cols-2">
            <h2 className="text-4xl font-medium leading-tight tracking-[-.05em] md:text-6xl">
              Design the conversation.
              <br />
              <span className="text-muted-foreground">See what happened.</span>
            </h2>
            <p className="max-w-md text-sm leading-7 text-muted-foreground md:justify-self-end md:self-end">
              One workspace for agent authoring, conversation testing and run
              evidence. Follow the transcript into the tools, flow visits and
              provider operations behind it.
            </p>
          </div>
          <div className="mt-12">
            <Suspense
              fallback={
                <p className="p-12 text-muted-foreground">
                  Loading product preview…
                </p>
              }
            >
              <RunPreview />
            </Suspense>
          </div>
          <div className="mt-4 flex flex-wrap justify-between gap-2 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            <span>Real Runs UI / Fictional demo data</span>
            <span>No customer records or credentials</span>
          </div>
          <div className="mt-12 grid gap-8">
            {["waterfall", "transcript"].map((view) => (
              <figure
                key={view}
                className="overflow-hidden border border-border bg-card"
              >
                <img
                  src={`/landing/runs-${view}.webp`}
                  alt={`Runs ${view} with provider spans and tool evidence`}
                  loading="lazy"
                  decoding="async"
                  width={view === "waterfall" ? 1828 : 1706}
                  height={view === "waterfall" ? 860 : 922}
                  className="h-auto w-full"
                />
                <figcaption className="p-6 font-mono text-xs text-muted-foreground">
                  Runs / {view} · Edited product screenshot · Anonymized data ·
                  Illustrative completed runs
                </figcaption>
              </figure>
            ))}
          </div>
          <h2 className="mt-16 text-4xl font-medium tracking-tight md:text-5xl">
            End-to-end voice agents for your business.
          </h2>
          <div className="mt-14 grid gap-10 md:grid-cols-3">
            {capabilities.map(({ icon: Icon, title, text, tags }) => (
              <article key={title} className="border-t border-border pt-7">
                <Icon className="size-6 text-primary" />
                <h3 className="mt-5 text-xl tracking-tight">{title}</h3>
                <p className="mt-3 text-sm leading-7 text-muted-foreground">
                  {text}
                </p>
                <p className="mt-5 font-mono text-[9px] tracking-widest text-primary">
                  {tags}
                </p>
              </article>
            ))}
          </div>
        </FadeContent>
      </section>
      <Architecture />
      <section
        id="connectivity"
        className="scroll-mt-8 border-y border-border bg-card"
      >
        <div
          className={cn(
            gutter,
            "grid items-center gap-12 py-20 lg:grid-cols-2",
          )}
        >
          <FadeContent>
            <p className={eyebrow}>03 / Beyond the browser</p>
            <h2 className="mt-5 text-4xl font-medium leading-tight tracking-[-.05em] md:text-6xl">
              Cloud calling.
              <br />
              <span className="text-muted-foreground">Local testing.</span>
              <br />
              One engine.
            </h2>
            <p className="mt-6 max-w-md text-sm leading-7 text-muted-foreground">
              Twilio connects cloud calls. I use a SIM7600 modem to test real
              cellular calls from a locally hosted Windows runtime.
            </p>
            <div className="mt-9 flex flex-col gap-6">
              <div className="flex gap-4">
                <Radio className="mt-1 size-5 shrink-0 text-primary" />
                <div>
                  <h3 className="text-sm">SIM7600 / my local test setup</h3>
                  <p className="mt-2 text-xs leading-6 text-muted-foreground">
                    SIM card, cellular network and native modem adapter.
                    Hardware, drivers and carrier support determine
                    compatibility.
                  </p>
                </div>
              </div>
              <div className="flex gap-4">
                <Cpu className="mt-1 size-5 shrink-0 text-primary" />
                <div>
                  <h3 className="text-sm">Twilio / cloud transport</h3>
                  <p className="mt-2 text-xs leading-6 text-muted-foreground">
                    Provider call lifecycle, media streaming and authenticated
                    callbacks connect to the conversation pipeline.
                  </p>
                </div>
              </div>
            </div>
            <a
              href={product}
              target="_blank"
              rel="noreferrer"
              className="mt-8 inline-flex items-center gap-2 text-xs text-primary underline-offset-4 hover:underline"
            >
              Explore the Waveshare HAT
              <ArrowUpRight className="size-4" />
            </a>
          </FadeContent>
          <FadeContent>
            <figure>
              <img
                src="/landing/waveshare-waves.webp"
                width="1448"
                height="1086"
                alt="Waveshare SIM7600 modem floating above soft blue signal waves"
                loading="lazy"
                className="w-full"
              />
              <figcaption className="mt-4 border-t border-border pt-4 font-mono text-[10px] leading-6 text-muted-foreground">
                WAVESHARE SIM7600G-H M.2 4G HAT
                <br />
                Manufacturer photograph with edited background · Local call
                testing.
              </figcaption>
            </figure>
          </FadeContent>
        </div>
      </section>
      <section
        className={cn(gutter, "grid gap-12 py-24 md:grid-cols-2 md:py-32")}
      >
        <FadeContent>
          <p className={eyebrow}>04 / Extend the control plane</p>
          <h2 className="mt-5 text-4xl font-medium tracking-[-.05em] md:text-5xl">
            Your tools.
            <br />
            Your agents.
            <br />
            <span className="text-muted-foreground">
              Connected through MCP.
            </span>
          </h2>
          <p className="mt-6 max-w-md text-sm leading-7 text-muted-foreground">
            Connect an MCP client to reviewed dashboard operations. Inspect
            selected run evidence and author configurations with user-bound,
            revocable access.
          </p>
          <div className="mt-7 flex flex-col gap-3 text-xs text-muted-foreground">
            {[
              "Live organization membership checks",
              "Tenant-scoped reads and reviewed mutations",
              "Audited access and revocable tokens",
            ].map((text) => (
              <p key={text} className="flex items-center gap-3">
                <Check className="size-4 text-primary" />
                {text}
              </p>
            ))}
          </div>
        </FadeContent>
        <FadeContent className="self-center border border-border bg-card">
          <div className="flex justify-between border-b border-border p-5 font-mono text-[10px] text-muted-foreground">
            <span>CONTROL PLANE / MCP</span>
            <Terminal className="size-4 text-primary" />
          </div>
          <div className="flex flex-col gap-5 p-7 font-mono text-xs leading-7">
            <p className="text-muted-foreground">
              // A scoped path from client to evidence
            </p>
            <p>
              <span className="text-primary">MCP client</span>
              <br />
              &nbsp; → User + organization authorization
              <br />
              &nbsp; → Reviewed API operation
              <br />
              &nbsp; → Selected run evidence
            </p>
            <div className="border-t border-border pt-5 text-muted-foreground">
              Configuration · Tools · Knowledge
              <br />
              Transcripts · Flow visits · Diagnostics
            </div>
            <p className="text-[10px] text-muted-foreground">
              Credential writes and runtime administration are excluded.
            </p>
          </div>
        </FadeContent>
      </section>
      <section className="relative overflow-hidden border-t border-border">
        <div className="pointer-events-none absolute inset-0 bg-radial-[at_70%_100%] from-primary/15 via-transparent to-transparent" />
        <FadeContent className={cn(gutter, "relative py-24 md:py-32")}>
          <p className={eyebrow}>Build the next conversation</p>
          <h2 className="mt-6 max-w-4xl text-5xl font-medium leading-[1.05] tracking-[-.06em] md:text-8xl">
            What would you build
            <br />
            if it could <span className="text-primary">speak?</span>
          </h2>
          <div className="mt-9 flex flex-wrap items-center gap-6">
            <Entry large />
            <a
              href={github}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-2 text-sm"
            >
              <Code2 className="size-4" />
              Explore the source
              <ArrowUpRight className="size-4" />
            </a>
          </div>
          <p className="mt-10 max-w-xl text-xs leading-6 text-muted-foreground">
            An evolving engineering project. Live calling requires configured
            providers or compatible hardware; deployment and call acceptance
            depend on the environment.
          </p>
        </FadeContent>
      </section>
      <footer
        className={cn(
          gutter,
          "flex flex-col justify-between gap-6 border-t border-border py-8 sm:flex-row sm:items-center",
        )}
      >
        <Brand />
        <p className="font-mono text-[10px] tracking-widest text-muted-foreground">
          ENGINEERED BY OMKAR · VOICE AI
        </p>
        <a
          href="#architecture"
          className="text-xs text-muted-foreground hover:text-primary"
        >
          Explore the architecture ↗
        </a>
      </footer>
    </div>
  );
}
