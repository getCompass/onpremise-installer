import { useRef } from "react";
import { cn } from "@/lib/utils.ts";

function ImagePreview({ triggerClassName, url }: { triggerClassName: string; url: string }) {
    const dialogRef = useRef<HTMLDialogElement>(null);

    const open = () => {
        dialogRef.current?.showModal();
    };
    const close = () => {
        if (dialogRef.current?.open) dialogRef.current.close();
    };

    return (
        <>
            <div
                className={cn("cursor-pointer", triggerClassName)}
                onClick={open}
            />

            <dialog
                ref={dialogRef}
                data-dialog="image-preview"
                className="p-0 border-none bg-transparent translate-x-[-50%] translate-y-[-50%] left-1/2 top-1/2 outline-none select-none default-dialog"
                onClick={(e) => {
                    if (e.target === dialogRef.current) {
                        close();
                    }
                }}
            >
                <img
                    src={url}
                    className="max-w-[90vw] max-h-[90vh] block"
                    onClick={() => dialogRef.current?.close()}
                />
            </dialog>
        </>
    );
}

export default ImagePreview;