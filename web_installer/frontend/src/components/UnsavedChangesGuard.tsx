import { useEffect, useRef, useState } from "react";

type Props = { active: boolean };

type PendingAction =
    | { type: "href"; href: string }
    | { type: "back" }
    | null;

export default function UnsavedChangesGuard({ active }: Props) {
    const [ _, setOpen ] = useState(false);
    const pendingRef = useRef<PendingAction>(null);

    const ignoreNextPop = useRef(false);

    useEffect(() => {
        if (!active) return;
        const onBeforeUnload = (e: BeforeUnloadEvent) => {
            e.preventDefault();
            e.returnValue = "";
        };
        window.addEventListener("beforeunload", onBeforeUnload);
        return () => window.removeEventListener("beforeunload", onBeforeUnload);
    }, [ active ]);

    // перехват кликов по <a> внутри SPA — показываем CustomDialog
    useEffect(() => {
        if (!active) return;

        const onClick = (e: MouseEvent) => {
            if (
                e.defaultPrevented ||
                e.button !== 0 ||
                e.metaKey ||
                e.ctrlKey ||
                e.shiftKey ||
                e.altKey
            )
                return;

            let el = e.target as HTMLElement | null;
            while (el && el.tagName !== "A") el = el.parentElement;
            const a = el as HTMLAnchorElement | null;
            if (!a || !a.href) return;

            const target = a.getAttribute("target");
            const href = a.getAttribute("href") || "";
            if (
                target === "_blank" ||
                href.startsWith("#") ||
                href.startsWith("mailto:") ||
                href.startsWith("tel:")
            )
                return;

            const sameOrigin = a.origin === window.location.origin;
            if (sameOrigin) {
                e.preventDefault();
                pendingRef.current = { type: "href", href: a.href };
                setOpen(true);
            }
        };

        document.addEventListener("click", onClick);
        return () => document.removeEventListener("click", onClick);
    }, [ active ]);

    // назад/вперед без unload (SPA)
    useEffect(() => {
        if (!active) return;

        const stopperState = { __unsaved_stop: Date.now() };
        history.pushState(stopperState, "");

        const onPopState = (e: PopStateEvent) => {
            // пропустить следующий popstate после forward/back
            if (ignoreNextPop.current) {
                ignoreNextPop.current = false;
                return;
            }

            // если мы вернулись НА стоппер (e.state содержит маркер) - это возврат вперёд
            // диалог показывать не нужно
            if (e.state && (e.state as any).__unsaved_stop) {
                return;
            }

            // уходим СТРОГО назад со стоппера - спрашиваем подтверждение
            pendingRef.current = { type: "back" };
            setOpen(true);
        };

        window.addEventListener("popstate", onPopState);
        return () => {
            window.removeEventListener("popstate", onPopState);
            if (history.state && (history.state as any).__unsaved_stop) {
                // аккуратно откатим фиктивную запись
                ignoreNextPop.current = true; // не всплывать лишний popstate при back()
                history.back();
            }
        };
    }, [ active ]);

    return null;
}
