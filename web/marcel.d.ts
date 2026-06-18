declare module "@marcel/web-components" {
  export const defineCustomElements: (opts?: any) => void;
}

namespace JSX {
  interface IntrinsicElements {
    "mrcl-badge": import("react").DetailedHTMLProps<import("react").HTMLAttributes<HTMLElement> & { variant?: string }, HTMLElement>;
    "mrcl-tag": import("react").DetailedHTMLProps<import("react").HTMLAttributes<HTMLElement> & { variant?: string }, HTMLElement>;
    "mrcl-button": import("react").DetailedHTMLProps<import("react").HTMLAttributes<HTMLElement> & { icon?: string; href?: string; className?: string }, HTMLElement>;
    "mrcl-modal": import("react").DetailedHTMLProps<import("react").HTMLAttributes<HTMLElement> & { open?: boolean; heading?: string }, HTMLElement>;
    "mrcl-drawer": import("react").DetailedHTMLProps<import("react").HTMLAttributes<HTMLElement> & { open?: boolean; position?: "left" | "right"; heading?: string }, HTMLElement>;
    "mrcl-tabs": import("react").DetailedHTMLProps<import("react").HTMLAttributes<HTMLElement>, HTMLElement>;
    "mrcl-tab": import("react").DetailedHTMLProps<import("react").HTMLAttributes<HTMLElement> & { label?: string; active?: boolean }, HTMLElement>;
    "mrcl-input-text": import("react").DetailedHTMLProps<import("react").HTMLAttributes<HTMLElement> & { label?: string; value?: string; placeholder?: string; disabled?: boolean; error?: string }, HTMLElement>;
    "mrcl-input-number": import("react").DetailedHTMLProps<import("react").HTMLAttributes<HTMLElement> & { label?: string; value?: number; min?: number; max?: number; disabled?: boolean }, HTMLElement>;
    "mrcl-select": import("react").DetailedHTMLProps<import("react").HTMLAttributes<HTMLElement> & { label?: string; value?: string; disabled?: boolean }, HTMLElement>;
    "mrcl-combobox": import("react").DetailedHTMLProps<import("react").HTMLAttributes<HTMLElement> & { label?: string; value?: string; placeholder?: string; disabled?: boolean }, HTMLElement>;
    "mrcl-textarea": import("react").DetailedHTMLProps<import("react").HTMLAttributes<HTMLElement> & { label?: string; value?: string; placeholder?: string; rows?: number; disabled?: boolean }, HTMLElement>;
    "mrcl-toaster": import("react").DetailedHTMLProps<import("react").HTMLAttributes<HTMLElement> & { message?: string; variant?: string; duration?: number }, HTMLElement>;
    "mrcl-toaster-container": import("react").DetailedHTMLProps<import("react").HTMLAttributes<HTMLElement> & { position?: string }, HTMLElement>;
    "mrcl-spinner": import("react").DetailedHTMLProps<import("react").HTMLAttributes<HTMLElement> & { size?: "sm" | "md" | "lg" }, HTMLElement>;
    "mrcl-skeleton": import("react").DetailedHTMLProps<import("react").HTMLAttributes<HTMLElement> & { width?: string; height?: string }, HTMLElement>;
    "mrcl-popover": import("react").DetailedHTMLProps<import("react").HTMLAttributes<HTMLElement> & { open?: boolean; placement?: string }, HTMLElement>;
    "mrcl-checkbox": import("react").DetailedHTMLProps<import("react").HTMLAttributes<HTMLElement> & { label?: string; checked?: boolean; disabled?: boolean }, HTMLElement>;
    "mrcl-toggle": import("react").DetailedHTMLProps<import("react").HTMLAttributes<HTMLElement> & { label?: string; checked?: boolean; disabled?: boolean }, HTMLElement>;
  }
}
