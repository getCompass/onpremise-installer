import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"
import type { ComponentProps } from "react";

const textVariants = cva(
    "outline-none",
    {
        variants: {
            variant: {
                default: "font-lato-regular",
                bold: "font-lato-bold",
                heavy: "font-lato-heavy",
                black: "font-lato-black",
            },
            size: {
                default: "text-[15px] leading-[21px]",
                xs: "text-[12px] leading-[18px]",
                s: "text-[14px] leading-[20px]",
                sm: "text-[15px] leading-[18px]",
                sm_heavy: "text-[15px] leading-[22px]",
                m: "text-[16px] leading-[19px]",
                m_black: "text-[18px] leading-[24px]",
                xl: "text-[20px] leading-[24px]",
                xxl: "text-[24px] leading-[31px]",
                tooltip: "text-[14px] leading-[18px]",
            },
            color: {
                default: "text-[rgba(255,255,255,0.8)]",
                white: "text-[#ffffff]",
                inactive: "text-[rgba(255,255,255,0.3)]",
                warning: "text-[#ff9d14]",
                error: "text-[#ff4f47]",
                link: "text-[#009fe6]",
            }
        },
        defaultVariants: {
            variant: "default",
            size: "default",
            color: "default",
        },
    }
)

function Text({
    className,
    variant,
    size,
    color,
    ...props
}: ComponentProps<"div"> &
    VariantProps<typeof textVariants> & {
    asChild?: boolean
}) {

    return (
        <div
            data-slot="text"
            className={cn(textVariants({ variant, size, color, className }))}
            {...props}
        />
    )
}

export { Text, textVariants }
