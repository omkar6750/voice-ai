import { Link } from "react-router-dom";

const items = [
  { label: "Organization", href: "/settings/organization" },
  { label: "Provider credentials", href: "/settings/credentials" },
];

export function SettingsNavigation({ active }: { active: string }) {
  return (
    <nav
      aria-label="Settings sections"
      className="flex gap-1 overflow-x-auto border-b"
    >
      {items.map((item) => (
        <Link
          key={item.href}
          to={item.href}
          aria-current={active === item.href ? "page" : undefined}
          className={`shrink-0 border-b-2 px-3 py-3 text-sm transition-colors ${
            active === item.href
              ? "border-primary font-medium text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          {item.label}
        </Link>
      ))}
    </nav>
  );
}
