import * as ProgressPrimitive from "@radix-ui/react-progress"

import { cn } from "@/lib/utils"
import type { ComponentProps } from "react";

function Progress({
    className,
    classNameIndicator,
    value,
    ...props
}: ComponentProps<typeof ProgressPrimitive.Root> & {
    classNameIndicator?: string
}) {
    return (
        <ProgressPrimitive.Root
            data-slot="progress"
            className={cn(
                "bg-[#252732] relative h-[6px] w-full overflow-hidden rounded-full",
                className
            )}
            {...props}
        >
            <ProgressPrimitive.Indicator
                data-slot="progress-indicator"
                className={cn("bg-[rgba(255,255,255,0.8)] h-full w-full flex-1 transition-all rounded-[12px]",
                    classNameIndicator
                )}
                style={{ transform: `translateX(-${100 - (value || 0)}%)` }}
            />
        </ProgressPrimitive.Root>
    )
}

export { Progress }
