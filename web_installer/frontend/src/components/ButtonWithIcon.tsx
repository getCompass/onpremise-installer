import { Button } from "@/components/ui/button.tsx";
import { Text } from "@/components/ui/text.tsx";
import type { ComponentProps, ReactNode } from "react";

type ButtonWithIconProps = Omit<ComponentProps<typeof Button>, "children"> & {
    icon: ReactNode;
    text: string;
};

const ButtonWithIcon = ({
    icon,
    text,
    variant = "secondary",
    size = "flexible",
    className,
    ...rest
}: ButtonWithIconProps) => {

    return (
        <Button variant={variant} size={size}
                className={`flex flex-row gap-[8px] items-center justify-center ${className ?? ""}`} {...rest}>
            {icon}
            <Text size="s" className="tracking-[-0.15px]">{text}</Text>
        </Button>
    )
}

export default ButtonWithIcon;
