import { useNavigatePage, useNavigatePageContent } from "@/components/hooks.ts";
import { useSetAtom } from "jotai";
import {
    activateServerStatusState, INITIAL_JOB_STATUS_RESPONSE,
    isWelcomeSkippedState,
    jobIdState,
    jobStatusResponseState,
    progressBarState
} from "@/api/_stores.ts";

const useNavigatePages = () => {
    const { activePage, navigateToPage } = useNavigatePage();
    const { activePageContent, navigateToPageContent } = useNavigatePageContent();
    const setIsWelcomeSkipped = useSetAtom(isWelcomeSkippedState);
    const setProgressBar = useSetAtom(progressBarState);
    const setJobId = useSetAtom(jobIdState);
    const setActivateServerStatus = useSetAtom(activateServerStatusState);
    const setJobStatusResponse = useSetAtom(jobStatusResponseState);

    const navigateToNextPage = (success_install?: boolean): void => {

        switch (activePage) {

            case "welcome":
                setIsWelcomeSkipped(1);
                navigateToPage("install");
                navigateToPageContent("configure");
                break;

            case "install":

                switch (activePageContent) {

                    case "configure":
                        navigateToPageContent("install_in_progress");
                        break;

                    case "install_in_progress":

                        if (success_install === true) {
                            navigateToPageContent("install_success");
                        }
                        if (success_install === false) {
                            navigateToPageContent("install_failed");
                        }
                        break;

                    case "install_failed":

                        setJobId("");
                        setJobStatusResponse(INITIAL_JOB_STATUS_RESPONSE);
                        setActivateServerStatus("not_activated");
                        setProgressBar(0);
                        navigateToPageContent("configure");
                        break;

                    case "install_success":
                        break;

                    default:
                        navigateToPage("install");
                        navigateToPageContent("configure");
                        break;
                }
                break;

            default:
                navigateToPageContent("welcome");
                navigateToPage("welcome");
                break;
        }
    };
    return { navigateToNextPage };
};

export default useNavigatePages;
