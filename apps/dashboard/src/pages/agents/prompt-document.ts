import { Extension, Node, type JSONContent } from "@tiptap/core";
import Document from "@tiptap/extension-document";
import Text from "@tiptap/extension-text";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";

export function promptDocument(text: string): JSONContent {
  return {
    type: "doc",
    content: [
      { type: "promptText", content: text ? [{ type: "text", text }] : [] },
    ],
  };
}

// One native editable surface. Whitespace and reference syntax remain literal
// text; HTML and formatting never become part of the runtime prompt.
const PromptText = Node.create({
  name: "promptText",
  group: "block",
  content: "text*",
  code: true,
  whitespace: "pre",
  defining: true,
  parseHTML: () => [
    { tag: "div[data-prompt-text]", preserveWhitespace: "full" },
  ],
  renderHTML: () => ["div", { "data-prompt-text": "" }, 0],
  addKeyboardShortcuts() {
    const newline = () =>
      this.editor.commands.insertContent({ type: "text", text: "\n" });
    return {
      Enter: newline,
      "Shift-Enter": newline,
    };
  },
  addProseMirrorPlugins() {
    return [
      new Plugin({
        props: {
          handlePaste: (view, event) => {
            if (!view.editable || !event.clipboardData) return false;
            const text = event.clipboardData
              .getData("text/plain")
              .replace(/\r\n?/g, "\n");
            view.dispatch(view.state.tr.insertText(text));
            return true;
          },
        },
      }),
    ];
  },
});

type Catalog = { tools: string[]; variables: string[] };
export function promptExtensions(catalog: () => Catalog) {
  const References = Extension.create({
    name: "promptReferences",
    addProseMirrorPlugins() {
      return [
        new Plugin({
          key: new PluginKey("promptReferences"),
          state: {
            init: (_, state) => decorate(state.doc, catalog()),
            apply: (tr, previous) =>
              tr.docChanged || tr.getMeta("prompt-catalog")
                ? decorate(tr.doc, catalog())
                : previous,
          },
          props: {
            decorations(state) {
              return this.getState(state);
            },
          },
        }),
      ];
    },
  });
  return [
    Document.extend({ content: "promptText" }),
    PromptText,
    Text,
    References,
  ];
}

function decorate(doc: import("@tiptap/pm/model").Node, catalog: Catalog) {
  const decorations: Decoration[] = [];
  doc.descendants((node, pos) => {
    if (!node.isText) return;
    for (const match of node.text!.matchAll(
      /(?:#([a-z][a-z0-9_]*)\b)|(?:\{\{\s*([a-zA-Z0-9_.]+)\s*\}\})/g,
    )) {
      const valid = match[1]
        ? catalog.tools.includes(match[1])
        : catalog.variables.includes(match[2]);
      decorations.push(
        Decoration.inline(
          pos + match.index!,
          pos + match.index! + match[0].length,
          {
            class: valid
              ? "rounded bg-primary/25 text-foreground ring-1 ring-inset ring-primary/50"
              : "rounded bg-destructive/20 text-destructive ring-1 ring-inset ring-destructive/50 underline decoration-wavy",
            "data-prompt-reference": match[1] ? "tool" : "variable",
            title: valid
              ? match[1]
                ? "Bound tool"
                : "Available variable"
              : "Unbound reference",
          },
        ),
      );
    }
  });
  return DecorationSet.create(doc, decorations);
}
