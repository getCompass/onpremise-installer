import { useMemo } from "react";
import { cn } from "@/lib/utils.ts";

export type blockFilledStatus = "not-filled" | "success-filled" | "error-filled"
const BlockStatus = ({ status }: {
    status: blockFilledStatus
}) => {

    const img = useMemo(() => {

        switch (status) {

            case "success-filled":
                return "bg-block-status-success-filled-icon";

            case "error-filled":
                return "bg-block-status-error-filled-icon";

            default:
                return "bg-block-status-not-filled-icon";
        }
    }, [ status ])

    return (
        <div className={cn("w-[16px] h-[16px] bg-cover", img)} />
    )
}

export default BlockStatus;