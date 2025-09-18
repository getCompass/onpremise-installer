import * as SwitchPrimitive from "@radix-ui/react-switch"

import { cn } from "@/lib/utils"
import type { ComponentProps } from "react";

function Switch({
  className,
  ...props
}: ComponentProps<typeof SwitchPrimitive.Root>) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      tabIndex={-1}
      className={cn(
        "peer cursor-pointer data-[state=checked]:bg-[#4cd864] data-[state=unchecked]:bg-[rgba(240,240,240,0.05)] inline-flex h-[23px] w-[36px] shrink-0 items-center rounded-full border border-transparent transition-all outline-none disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        data-slot="switch-thumb"
        className={cn(
          "bg-[#ffffff] pointer-events-none block size-[19px] rounded-full ring-0 transition-transform data-[state=checked]:translate-x-[calc(100%-5px)] data-[state=unchecked]:translate-x-[1px]"
        )}
      />
    </SwitchPrimitive.Root>
  )
}

export { Switch }
