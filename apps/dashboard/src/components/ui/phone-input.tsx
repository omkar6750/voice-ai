import * as React from "react";
import { cn } from "cn";
import { Popover } from "radix-ui";
import { ChevronDownIcon, CheckIcon, SearchIcon } from "lucide-react";
import { COUNTRIES, detectCountry, type CountryInfo } from "@/lib/geo-data";

export interface PhoneInputProps {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  required?: boolean;
  disabled?: boolean;
  className?: string;
}

export function PhoneInput({
  id,
  value,
  onChange,
  placeholder = "9876543210",
  required = false,
  disabled = false,
  className,
}: PhoneInputProps) {
  const [open, setOpen] = React.useState(false);
  const [search, setSearch] = React.useState("");

  // Determine current active country based on current value
  const activeCountry = React.useMemo(() => {
    return detectCountry(value);
  }, [value]);

  // Extract the local part (after the dial code)
  const localNumber = React.useMemo(() => {
    const clean = value.trim();
    if (clean.startsWith(activeCountry.dialCode)) {
      return clean.slice(activeCountry.dialCode.length).trim();
    }
    if (clean.startsWith("+")) {
      return clean.replace(/^\+\d+/, "").trim();
    }
    return clean;
  }, [value, activeCountry]);

  // Filter countries for dropdown
  const filteredCountries = React.useMemo(() => {
    const q = search.toLowerCase().trim();
    if (!q) return COUNTRIES;
    return COUNTRIES.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        c.dialCode.includes(q) ||
        c.code.toLowerCase().includes(q)
    );
  }, [search]);

  const handleCountrySelect = (country: CountryInfo) => {
    setOpen(false);
    setSearch("");
    // Combine new country dial code with existing local number
    const updated = localNumber ? `${country.dialCode}${localNumber}` : country.dialCode;
    onChange(updated);
  };

  const handleNumberChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value;
    if (raw.startsWith("+")) {
      // User typed or pasted a full international number with +
      const cleaned = raw.replace(/[^\d+]/g, "");
      onChange(cleaned);
    } else {
      // User typed local number digits
      const digitsOnly = raw.replace(/\D/g, "");
      const full = digitsOnly ? `${activeCountry.dialCode}${digitsOnly}` : "";
      onChange(full);
    }
  };

  return (
    <div className={cn("flex w-full items-center rounded-lg border border-input bg-transparent text-sm focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/40 transition-colors", className)}>
      <Popover.Root open={open} onOpenChange={setOpen}>
        <Popover.Trigger asChild>
          <button
            type="button"
            disabled={disabled}
            className="flex shrink-0 items-center gap-1 border-r border-input bg-muted/40 hover:bg-muted/70 px-2.5 py-1 text-xs font-medium rounded-l-lg transition-colors h-8.5 select-none disabled:opacity-50"
            title={`${activeCountry.name} (${activeCountry.dialCode})`}
          >
            <span className="text-sm">{activeCountry.flag}</span>
            <span className="font-mono text-muted-foreground">{activeCountry.dialCode}</span>
            <ChevronDownIcon className="h-3 w-3 opacity-60 ml-0.5" />
          </button>
        </Popover.Trigger>

        <Popover.Portal>
          <Popover.Content
            align="start"
            sideOffset={4}
            className="z-50 w-64 max-h-64 overflow-hidden rounded-lg border bg-popover p-1 text-popover-foreground shadow-lg outline-none flex flex-col"
          >
            <div className="flex items-center gap-1.5 border-b px-2 py-1.5 shrink-0">
              <SearchIcon className="h-3.5 w-3.5 text-muted-foreground" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search country or code..."
                className="w-full bg-transparent text-xs outline-none placeholder:text-muted-foreground"
                autoFocus
              />
            </div>
            <div className="overflow-y-auto max-h-52 flex flex-col gap-0.5 p-1">
              {filteredCountries.map((c) => {
                const isSelected = c.code === activeCountry.code;
                return (
                  <button
                    key={c.code}
                    type="button"
                    onClick={() => handleCountrySelect(c)}
                    className={cn(
                      "flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors",
                      isSelected
                        ? "bg-accent text-accent-foreground font-medium"
                        : "hover:bg-muted/60 text-foreground"
                    )}
                  >
                    <div className="flex items-center gap-2 truncate">
                      <span className="text-sm shrink-0">{c.flag}</span>
                      <span className="truncate">{c.name}</span>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <span className="text-[11px] font-mono text-muted-foreground">
                        {c.dialCode}
                      </span>
                      {isSelected && <CheckIcon className="h-3 w-3 text-primary" />}
                    </div>
                  </button>
                );
              })}
              {filteredCountries.length === 0 && (
                <div className="p-3 text-center text-xs text-muted-foreground">
                  No countries found
                </div>
              )}
            </div>
          </Popover.Content>
        </Popover.Portal>
      </Popover.Root>

      <input
        id={id}
        type="tel"
        value={localNumber}
        onChange={handleNumberChange}
        disabled={disabled}
        required={required}
        placeholder={placeholder}
        className="h-8.5 w-full bg-transparent px-2.5 py-1 text-sm outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50"
      />
    </div>
  );
}
