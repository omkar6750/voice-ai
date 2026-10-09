// Adapted from React Bits BlurText and FadeContent (David Haz).
// Sources and license: ./LICENSE.txt and ./README.md.
// Native Web Animations replace motion/GSAP to keep this public page small.
import { useEffect, useRef, type ReactNode, type ComponentProps } from "react";

export function FloatingHardware(props: ComponentProps<"img">) {
  const ref = useRef<HTMLImageElement>(null);
  useEffect(() => {
    const node = ref.current;
    if (!node || !node.animate || !window.IntersectionObserver) return;
    const preference = window.matchMedia(
      "(prefers-reduced-motion: reduce), (max-width: 767px)",
    );
    let animation: Animation | undefined;
    let visible = false;
    const update = () => {
      animation?.cancel();
      if (preference.matches || !visible || document.hidden) return;
      animation = node.animate(
        [
          { transform: "translateY(0) rotate(-2deg)" },
          { transform: "translateY(-14px) rotate(0deg)" },
          { transform: "translateY(0) rotate(-2deg)" },
        ],
        { duration: 6500, iterations: Infinity, easing: "ease-in-out" },
      );
    };
    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      update();
    });
    observer.observe(node);
    preference.addEventListener("change", update);
    document.addEventListener("visibilitychange", update);
    return () => {
      observer.disconnect();
      animation?.cancel();
      preference.removeEventListener("change", update);
      document.removeEventListener("visibilitychange", update);
    };
  }, []);
  return <img ref={ref} {...props} />;
}

function useReveal(stagger = false) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (preference.matches || !window.IntersectionObserver || !node.animate)
      return;
    const targets = stagger ? Array.from(node.children) : [node];
    let animations: Animation[] = [];
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        animations = targets.map((target, index) =>
          target.animate(
            [
              {
                opacity: 0.25,
                transform: "translateY(24px)",
                filter: stagger ? "blur(8px)" : "none",
              },
              { opacity: 1, transform: "translateY(0)", filter: "blur(0px)" },
            ],
            {
              duration: 650,
              delay: stagger ? index * 100 : 0,
              easing: "cubic-bezier(.16,1,.3,1)",
              fill: "backwards",
            },
          ),
        );
        observer.disconnect();
      },
      { threshold: 0.12 },
    );
    const stop = () => animations.forEach((animation) => animation.cancel());
    preference.addEventListener("change", stop);
    observer.observe(node);
    return () => {
      observer.disconnect();
      stop();
      preference.removeEventListener("change", stop);
    };
  }, [stagger]);
  return ref;
}

export function FadeContent({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div ref={useReveal()} className={className}>
      {children}
    </div>
  );
}

export function BlurText({
  text,
  className,
}: {
  text: string;
  className?: string;
}) {
  return (
    <div ref={useReveal(true)} className={className} aria-label={text}>
      {text.split(" ").map((word, index) => (
        <span key={index} aria-hidden="true" className="inline-block">
          {word}
          {"\u00a0"}
        </span>
      ))}
    </div>
  );
}
