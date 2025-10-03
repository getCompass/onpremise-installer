import { type ReactNode, useEffect } from "react";
import { Tooltip } from "@/components/ui/tooltip.tsx";
import { Text } from "@/components/ui/text.tsx";
import { useLangString } from "@/lib/getLangString.ts";

const NoNetworkError = ({ visible, setVisible, triggerComponent }: {
    visible: boolean;
    setVisible: (v: boolean) => void;
    triggerComponent: ReactNode;
}) => {
    const t = useLangString();

    useEffect(() => {

        if (!visible) return;

        // скрываем
        window.setTimeout(() => {
            setVisible(false);
        }, 3000);
    }, [ visible ]);

    return (
        <div className="relative w-full flex justify-center">
            <Tooltip
                classNameContent="max-w-[219px] w-[219px]"
                color="orange"
                open={visible}
                side="top"
                sideOffset={-1}
            >
                <Text size="s" className="text-center tracking-[-0.15px]">
                    {t("no_network_error")}
                </Text>
            </Tooltip>
            {triggerComponent}
        </div>
    )
}

export default NoNetworkError;