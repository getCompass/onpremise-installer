import { cn } from "@/lib/utils"
import type { ComponentProps } from "react";

function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "placeholder:text-[rgba(255,255,255,0.3)] aria-invalid:ring-destructive/20 aria-invalid:border-destructive flex w-full scrollbar-hidden h-auto min-h-0 bg-transparent text-[rgba(255,255,255,0.8)] text-[15px] transition-[color,box-shadow] outline-none disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      {...props}
    />
  )
}

export { Textarea }
