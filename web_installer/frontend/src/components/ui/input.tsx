import type { ComponentProps } from "react";

import { cn } from "@/lib/utils"

function Input({ className, type, ...props }: ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "file:text-foreground placeholder:text-[rgba(255,255,255,0.3)] selection:bg-primary selection:text-primary-foreground flex h-[18px] w-full min-w-0 bg-transparent text-[rgba(255,255,255,0.8)] text-[15px] font-lato-regular transition-[color,box-shadow] outline-none file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-lato-regular disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50",
        "aria-invalid:ring-destructive/20 aria-invalid:border-destructive",
        className
      )}
      {...props}
    />
  )
}

export { Input }
