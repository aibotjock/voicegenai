import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "icon";
type Size = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  children?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    { variant = "secondary", size = "md", className = "", type = "button", ...rest },
    ref,
  ) {
    const cls = [
      "btn",
      variant === "icon" ? "btn-icon" : `btn-${variant}`,
      size === "lg" ? "btn-lg" : size === "sm" ? "btn-sm" : "",
      className,
    ]
      .filter(Boolean)
      .join(" ");
    return <button ref={ref} type={type} className={cls} {...rest} />;
  },
);
