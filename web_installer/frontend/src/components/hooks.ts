import { useCallback } from "react";
import { atom, useAtom } from "jotai";

export type PageContent =
    | "welcome"
    | "configure"
    | "install_in_progress"
    | "install_failed"
    | "install_success";

const activePageContentState = atom<PageContent>("welcome");

export function useNavigatePageContent() {

    const [ activePageContent, setActivePageContent ] = useAtom(activePageContentState);

    const navigateToPageContent = useCallback(
        (pageContent: PageContent) => {

            setActivePageContent(pageContent);
        },
        [ activePageContent ]
    );

    return { activePageContent, navigateToPageContent };
}

export type Page =
    | "welcome"
    | "install";

const activePageState = atom<Page>("welcome");

export function useNavigatePage() {

    const [ activePage, setActivePage ] = useAtom(activePageState);

    const navigateToPage = useCallback(
        (page: Page) => {

            setActivePage(page);
        }, [ activePage ]
    );

    return { activePage, navigateToPage };
}
