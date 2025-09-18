import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"
import type { ComponentProps } from "react";

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-[8px] text-[15px] leading-[23px] font-lato-regular cursor-pointer disabled:cursor-default disabled:pointer-events-none [&_svg]:pointer-events-none shrink-0 [&_svg]:shrink-0 outline-none",
  {
    variants: {
      variant: {
        primary:
          "bg-[#006be0] hover:bg-[#0058b8] text-[#ffffff]",
        secondary:
            "bg-[rgba(0,0,0,0.1)] hover:bg-[rgba(0,0,0,0.2)]",
        dialog:
            "bg-transparent hover:bg-[rgba(255,255,255,0.02)] border-[rgba(255,255,255,0.1)] border-[1px]",
        text:"text-[rgba(255,255,255,0.5)] hover:text-[rgba(255,255,255,0.8)]",
        secondary_cancel: "bg-[rgba(255,255,255,0.04)] hover:bg-[rgba(255,255,255,0.1)] text-[#b4b4b4]",
      },
      size: {
        primary: "w-full py-[6px] px-[16px]",
        dialog: "w-full py-[5px] px-[14px]",
        flexible: "px-[16px] py-[8px]",
        lg: "h-10 rounded-md px-6 has-[>svg]:px-4",
        icon: "size-9",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "primary",
    },
  }
)

function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot : "button"

  return (
    <Comp
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
