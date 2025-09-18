import { Dialog, DialogContent, DialogTitle, DialogTrigger } from "@/components/ui/dialog.tsx";
import type { FC, ReactNode } from "react";
import { VisuallyHidden } from "@radix-ui/react-visually-hidden";

type CustomDialogProps = {
    trigger?: ReactNode | null;
    content: ReactNode;
    classNameContent?: string;
    open?: boolean;
    onOpenChange?: (open: boolean) => void;
    modal?: boolean;
    preventClose?: boolean;
    showCloseButton?: boolean;
};

const CustomDialog: FC<CustomDialogProps> = ({
    trigger,
    content,
    classNameContent,
    open,
    onOpenChange,
    modal = true,
    preventClose = false,
    showCloseButton = true,
}) => {

    const handleInteractOutside = (e: Event) => {
        if (preventClose) e.preventDefault();
    };
    const handleEscapeKeyDown = (e: KeyboardEvent) => {
        if (preventClose) e.preventDefault();
    };

    const handleCloseAutoFocus = (e: Event) => {
        e.preventDefault();
    };

    return (
        <Dialog
            open={open}
            onOpenChange={onOpenChange}
            modal={modal}
        >
            {trigger ? (
                <DialogTrigger asChild className="outline-none">
                    {trigger}
                </DialogTrigger>
            ) : null}

            <DialogContent
                className={`w-[360px] ${classNameContent ?? ""}`}
                aria-describedby={undefined}
                onInteractOutside={handleInteractOutside}
                onEscapeKeyDown={handleEscapeKeyDown}
                onCloseAutoFocus={handleCloseAutoFocus}
                showCloseButton={showCloseButton}
            >
                <VisuallyHidden asChild>
                    <DialogTitle>Dialog</DialogTitle>
                </VisuallyHidden>
                {content}
            </DialogContent>
        </Dialog>
    );
};

export default CustomDialog;
