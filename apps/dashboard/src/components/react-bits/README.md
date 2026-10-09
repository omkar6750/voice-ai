# React Bits adaptations

Reviewed the upstream TypeScript/Tailwind catalog on 2026-10-09. Selected
[Blur Text](https://reactbits.dev/text-animations/blur-text) and
[Fade Content](https://reactbits.dev/animations/fade-content).

Upstream source: https://github.com/DavidHDev/react-bits/tree/main/src/ts-tailwind

Motion.tsx adapts their word-stagger and intersection-triggered reveal patterns
to native Web Animations. No GSAP, WebGL or motion library is loaded. Content
stays visible without animation APIs. Effects run once, cancel on unmount and
respect changes to reduced-motion preferences. The upstream license is retained.
