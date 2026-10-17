const inputElements = {
  formFieldInput: "bg-muted! text-foreground! caret-foreground! placeholder:text-muted-foreground! [-webkit-text-fill-color:var(--foreground)]! autofill:[-webkit-text-fill-color:var(--foreground)]!",
  identityPreviewText: "text-foreground!",
};

export const clerkAppearance = {
  variables: {
    colorPrimary: "#315efb",
    colorForeground: "#172033",
    colorBackground: "#f8f9fb",
    colorInput: "#ffffff",
    colorInputForeground: "#172033",
    borderRadius: "0.75rem",
  },
  elements: inputElements,
};

export const clerkAuthAppearance = {
  variables: {
    colorPrimary: "#52a8ff",
    colorPrimaryForeground: "#000000",
    colorBackground: "#0a0a0a",
    colorForeground: "#ededed",
    colorNeutral: "#ededed",
    colorMutedForeground: "#999999",
    colorInput: "#1f1f1f",
    colorInputForeground: "#ededed",
    borderRadius: "0px",
  },
  elements: inputElements,
};
