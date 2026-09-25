import * as React from "react";
import { cn } from "cn";
import { Popover } from "radix-ui";
import { ChevronDownIcon, CheckIcon, XIcon } from "lucide-react";
import type { OptionItem } from "@/lib/geo-data";

export interface SearchableSelectProps {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  options: OptionItem[];
  placeholder?: string;
  className?: string;
  disabled?: boolean;
  required?: boolean;
  emptyText?: string;
}

export function SearchableSelect({
  id,
  value,
  onChange,
  options,
  placeholder = "Select or type...",
  className,
  disabled = false,
  required = false,
  emptyText = "No matches found. Custom value will be kept.",
}: SearchableSelectProps) {
  const [open, setOpen] = React.useState(false);
  const [activeIndex, setActiveIndex] = React.useState(-1);
  const [isTyping, setIsTyping] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);

  // Normalize query
  const query = value.toLowerCase().trim();

  // Check if current value exactly matches an option
  const isSelectedOption = React.useMemo(() => {
    return options.some(
      (opt) =>
        opt.value.toLowerCase() === query ||
        opt.label.toLowerCase() === query
    );
  }, [options, query]);

  // Filter options
  const filtered = React.useMemo(() => {
    // When empty OR when browsing without actively typing a search filter
    if (!query || (isSelectedOption && !isTyping)) {
      return options;
    }

    const cleanQuery = query.replace(/[_\s/]+/g, " ").trim();
    return options.filter((opt) => {
      const optVal = opt.value.toLowerCase().replace(/[_\s/]+/g, " ");
      const optLabel = opt.label.toLowerCase().replace(/[_\s/]+/g, " ");
      const optSub = (opt.sublabel || "").toLowerCase();
      const hasKeyword = opt.keywords?.some((k) => {
        const cleanK = k.toLowerCase().replace(/[_\s/]+/g, " ");
        return cleanK.includes(cleanQuery) || cleanQuery.includes(cleanK);
      });

      return (
        optVal.includes(cleanQuery) ||
        optLabel.includes(cleanQuery) ||
        optSub.includes(cleanQuery) ||
        Boolean(hasKeyword)
      );
    });
  }, [options, query, isSelectedOption, isTyping]);

  const handleSelect = (val: string) => {
    onChange(val);
    setIsTyping(false);
    setOpen(false);
    setActiveIndex(-1);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!open) {
        setOpen(true);
      } else {
        setActiveIndex((prev) =>
          prev < filtered.length - 1 ? prev + 1 : prev
        );
      }
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (open) {
        setActiveIndex((prev) => (prev > 0 ? prev - 1 : 0));
      }
    } else if (e.key === "Enter") {
      if (open && activeIndex >= 0 && activeIndex < filtered.length) {
        e.preventDefault();
        handleSelect(filtered[activeIndex].value);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
      setActiveIndex(-1);
    }
  };

  return (
    <Popover.Root
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          setIsTyping(false);
          setActiveIndex(-1);
        }
      }}
    >
      <Popover.Anchor asChild>
        <div className={cn("relative flex items-center w-full", className)}>
          <input
            ref={inputRef}
            id={id}
            type="text"
            value={value}
            disabled={disabled}
            required={required}
            placeholder={placeholder}
            autoComplete="off"
            onChange={(e) => {
              onChange(e.target.value);
              setIsTyping(true);
              if (!open) setOpen(true);
              setActiveIndex(-1);
            }}
            onFocus={(e) => {
              e.target.select();
              setOpen(true);
            }}
            onKeyDown={handleKeyDown}
            className={cn(
              "h-8.5 w-full rounded-lg border border-input bg-transparent px-2.5 py-1 text-sm transition-colors",
              "placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/40 focus-visible:outline-none",
              "disabled:cursor-not-allowed disabled:opacity-50 pr-14"
            )}
          />
          <div className="absolute right-1.5 flex items-center gap-0.5 text-muted-foreground">
            {value && !disabled && (
              <button
                type="button"
                tabIndex={-1}
                onClick={(e) => {
                  e.stopPropagation();
                  onChange("");
                  setIsTyping(true);
                  inputRef.current?.focus();
                }}
                className="p-1 hover:text-foreground rounded-sm transition-colors"
                title="Clear"
              >
                <XIcon className="h-3.5 w-3.5" />
              </button>
            )}
            <button
              type="button"
              tabIndex={-1}
              onClick={(e) => {
                e.stopPropagation();
                setIsTyping(false);
                setOpen((prev) => !prev);
                inputRef.current?.focus();
              }}
              className="p-1 hover:text-foreground rounded-sm transition-colors"
              title="Toggle list"
            >
              <ChevronDownIcon className="h-3.5 w-3.5 opacity-60" />
            </button>
          </div>
        </div>
      </Popover.Anchor>

      <Popover.Portal>
        <Popover.Content
          align="start"
          sideOffset={4}
          onOpenAutoFocus={(e) => e.preventDefault()}
          className="z-50 w-[var(--radix-popover-anchor-width)] max-h-56 overflow-y-auto rounded-lg border bg-popover p-1 text-popover-foreground shadow-lg outline-none"
        >
          {filtered.length === 0 ? (
            <div className="px-3 py-2 text-xs text-muted-foreground">
              {emptyText}
            </div>
          ) : (
            <div className="flex flex-col gap-0.5">
              {filtered.map((item, idx) => {
                const isSelected = item.value === value;
                const isHighlighted = idx === activeIndex;
                return (
                  <button
                    key={item.value}
                    type="button"
                    onClick={() => handleSelect(item.value)}
                    className={cn(
                      "flex w-full items-center justify-between gap-2 rounded-md px-2.5 py-1.5 text-left text-xs transition-colors",
                      isHighlighted || isSelected
                        ? "bg-accent text-accent-foreground font-medium"
                        : "hover:bg-muted/60 text-foreground"
                    )}
                  >
                    <span className="truncate flex-1">
                      {item.badge ? `${item.badge} ` : ""}
                      {item.label}
                    </span>
                    <div className="flex items-center gap-1.5 shrink-0">
                      {item.sublabel && (
                        <span className="text-[10px] text-muted-foreground bg-muted/80 px-1.5 py-0.5 rounded font-mono">
                          {item.sublabel}
                        </span>
                      )}
                      {isSelected && <CheckIcon className="h-3.5 w-3.5 text-primary" />}
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
