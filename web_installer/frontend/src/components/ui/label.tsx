import * as LabelPrimitive from "@radix-ui/react-label"

import { cn } from "@/lib/utils"
import type { ComponentProps } from "react";

function Label({
    className,
    ...props
}: ComponentProps<typeof LabelPrimitive.Root>) {
    return (
        <LabelPrimitive.Root
            data-slot="label"
            className={cn(
                "text-[15px] text-[rgba(255,255,255,0.8)] leading-none font-lato-regular select-none group-data-[disabled=true]:pointer-events-none group-data-[disabled=true]:opacity-50 peer-disabled:cursor-not-allowed peer-disabled:opacity-50",
                className
            )}
            {...props}
        />
    )
}

export { Label }
