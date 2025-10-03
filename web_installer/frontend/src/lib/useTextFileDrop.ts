import { useLangString } from "@/lib/getLangString.ts";
import { type DragEvent, useState } from "react";

export const AllowedFileExtension = /\.(txt|log|pem|crt|cer|key|cfg|conf|cnf)$/i;
export const ProhibitedFileExtension = /\.(sh|py|php|xml)$/i;

type Options = {
    onText: (text: string, file: File) => void;
    maxBytes?: number; // ограничение размера, например: 10_000_000
    nameAllow?: RegExp; // фильтр по имени, например, /\.(pem|crt|cer|key|txt)$/i
};

export default function useTextFileDrop({ onText, maxBytes = 10_000_000, nameAllow }: Options) {
    const t = useLangString();
    const [ isOver, setIsOver ] = useState(false);
    const [ error, setError ] = useState<string | null>(null);

    const prevent = (e: DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
    };

    const onDragEnter = (e: DragEvent) => {
        prevent(e);
        setIsOver(true);
    };
    const onDragOver = (e: DragEvent) => {
        prevent(e);
        setIsOver(true);
    };
    const onDragLeave = (e: DragEvent) => {
        prevent(e);
        setIsOver(false);
    };

    const onDrop = async (e: DragEvent) => {
        prevent(e);
        setIsOver(false);
        setError(null);

        const file = e.dataTransfer.files?.[0];
        if (!file) return;

        // разрешаем «text/*» и часто используемые текстовые расширения
        const looksText =
            file.type.startsWith("text/") ||
            AllowedFileExtension.test(file.name);
        const executedFiles = ProhibitedFileExtension.test(file.name);

        const allowedByName = nameAllow ? nameAllow.test(file.name) : true;

        if (!looksText || !allowedByName || executedFiles) {
            setError(t("install_page.configure.domain_block.ssl_upload_file_error_extension"));
            return;
        }
        if (file.size > maxBytes) {
            setError(t("install_page.configure.domain_block.ssl_upload_file_error_size"));
            return;
        }

        try {
            const text = await file.text();
            onText(text, file);
        } catch {
            setError(t("install_page.configure.domain_block.ssl_upload_file_error_general"));
        }
    };

    // пропсы
    const dropProps = { onDragEnter, onDragOver, onDragLeave, onDrop };

    return { isOver, error, dropProps, setError };
}
