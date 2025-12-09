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
                className={cn("relative bg-[rgba(255,255,255,0.75)] h-full w-full flex-1 overflow-hidden rounded-[12px]",
                    classNameIndicator
                )}
                style={{ transform: `translateX(-${100 - (value || 0)}%)` }}
            >
                <span className="progress-bar-slide block h-full w-full" />
            </ProgressPrimitive.Indicator>
        </ProgressPrimitive.Root>
    )
}

export { Progress }
