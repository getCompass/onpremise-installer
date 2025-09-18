import * as TooltipPrimitive from "@radix-ui/react-tooltip"

import { cn } from "@/lib/utils"
import type { ComponentProps, ReactNode } from "react";

function TooltipProvider({
    delayDuration = 0,
    ...props
}: ComponentProps<typeof TooltipPrimitive.Provider>) {
    return (
        <TooltipPrimitive.Provider
            data-slot="tooltip-provider"
            delayDuration={delayDuration}
            {...props}
        />
    )
}

function Tooltip({
    trigger,
    children,
    side = "top",
    sideOffset = 0,
    classNameContent,
    classNameTrigger,
    ...props
}: ComponentProps<typeof TooltipPrimitive.Root> & {
    trigger?: ReactNode;
    side?: "top" | "bottom" | "left" | "right";
    sideOffset?: number;
    classNameContent?: string;
    classNameTrigger?: string;
}) {
    return (
        <TooltipProvider>
            <TooltipPrimitive.Root data-slot="tooltip" {...props}>
                <TooltipTrigger className={cn(classNameTrigger, trigger == null ? "absolute" : "")} tabIndex={-1}>
                    {trigger}
                </TooltipTrigger>
                <TooltipContent className={classNameContent} sideOffset={sideOffset} side={side}>
                    {children}
                </TooltipContent>
            </TooltipPrimitive.Root>
        </TooltipProvider>
    )
}

function TooltipTrigger({
    className,
    ...props
}: ComponentProps<typeof TooltipPrimitive.Trigger>) {
    return <TooltipPrimitive.Trigger data-slot="tooltip-trigger" className={cn(
        "align-text-bottom",
        className
    )} {...props} />
}

function TooltipContent({
    className,
    sideOffset = 0,
    children,
    ...props
}: ComponentProps<typeof TooltipPrimitive.Content>) {
    return (
        <TooltipPrimitive.Portal>
            <TooltipPrimitive.Content
                data-slot="tooltip-content"
                sideOffset={sideOffset}
                className={cn(
                    "bg-[#1a1c23] text-[rgba(255,255,255,0.8)] animate-in fade-in-0 zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2 z-48 w-fit origin-(--radix-tooltip-content-transform-origin) rounded-[8px] px-[12px] py-[8px]",
                    className
                )}
                {...props}
            >
                {children}
                <TooltipPrimitive.Arrow
                    className="bg-[#1a1c23] fill-[#1a1c23] z-48 size-2.5 translate-y-[calc(-50%_-_2px)] rotate-45" />
            </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
    )
}

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider }
