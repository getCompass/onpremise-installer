import * as CheckboxPrimitive from "@radix-ui/react-checkbox"
import { CheckIcon } from "lucide-react"

import { cn } from "@/lib/utils"
import type { ComponentProps } from "react";

function Checkbox({
  className,
  ...props
}: ComponentProps<typeof CheckboxPrimitive.Root>) {
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      tabIndex={-1}
      className={cn(
        "peer data-[state=checked]:bg-[#006be0] data-[state=checked]:text-[#ffffff] data-[state=checked]:border-[#006be0] focus-visible:border-[#006be0] focus-visible:ring-ring/50 cursor-pointer aria-invalid:ring-destructive/20 aria-invalid:border-destructive size-[16px] shrink-0 rounded-[4px] border border-[#006be0] outline-none focus-visible:ring-[3px] disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator
        data-slot="checkbox-indicator"
        className="flex items-center justify-center text-current transition-none"
      >
        <CheckIcon className="size-3.5" />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  )
}

export { Checkbox }
