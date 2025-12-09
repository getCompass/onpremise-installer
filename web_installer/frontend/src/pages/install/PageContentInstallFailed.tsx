import { Text } from "@/components/ui/text.tsx";
import { useLangString } from "@/lib/getLangString.ts";
import { Progress } from "@/components/ui/progress.tsx";
import { useAtomValue } from "jotai";
import { activateServerStatusState, isSlowDiskSpeedState, jobIdState, progressBarState } from "@/api/_stores.ts";
import { Button } from "@/components/ui/button.tsx";
import useNavigatePages from "@/lib/navigatePages.ts";
import { useCallback, useMemo, useState } from "react";
import { useAtom, useSetAtom } from "jotai/index";
import { useNavigatePageContent } from "@/components/hooks.ts";
import Preloader from "@/components/Preloader.tsx";
import CustomDialog from "@/components/CustomDialog.tsx";
import { DialogClose } from "@/components/ui/dialog.tsx";
import NoNetworkError from "@/components/NoNetworkError.tsx";

type BackToConfigureResponse = {
    success: boolean;
    log?: string;
};

const PageContentInstallFailed = () => {
    const t = useLangString();
    const progressBar = useAtomValue(progressBarState);
    const { navigateToNextPage } = useNavigatePages()
    const { navigateToPageContent } = useNavigatePageContent();
    const [ activateServerStatus, _ ] = useAtom(activateServerStatusState);
    const setActivateServerStatus = useSetAtom(activateServerStatusState);
    const jobId = useAtomValue(jobIdState);
    const isSlowDiskSpeed = useAtomValue(isSlowDiskSpeedState);
    const [ loading, setLoading ] = useState<boolean>(false);
    const [ downloading, setDownloading ] = useState<boolean>(false);
    const [ logsDownloaded, setLogsDownloaded ] = useState<boolean>(false);
    const [ networkError, setNetworkError ] = useState(false);
    const [ activateNetworkError, setActivateNetworkError ] = useState(false);

    // true если упали на этапе установки
    // false если упали на этапе активации сервера
    const isFailedOnInstall = useMemo(() => {
        return activateServerStatus !== "failed";
    }, [ activateServerStatus ]);

    const backToConfigure = useCallback(async () => {
        setLoading(true);
        try {
            const resp = await fetch("/api/install/back_to_configure", {
                method: "POST",
            });
            const json = (await resp.json()) as BackToConfigureResponse;
            if (json.success) {

                setLogsDownloaded(false);
                navigateToNextPage();
                return;
            }
        } catch (e) {
            // игнорируем AbortError
            // @ts-expect-error
            if (e?.name !== "AbortError") {
                setNetworkError(true);
            }
            console.error("back_to_configure failed:", e);
        } finally {
            setLoading(false);
        }
    }, []);

    const tryActivateServerAgain = useCallback(async () => {

        try {
            // при активации сервера сначала проверяем есть ли интернет
            await fetch("/api/server/info");
        } catch (e) {
            // игнорируем AbortError
            // @ts-expect-error
            if (e?.name !== "AbortError") {
                setActivateNetworkError(true);
            }
            return;
        }

        setActivateServerStatus("not_activated");
        navigateToPageContent("install_in_progress");
    }, [])

    // скачиваем логи
    const downloadLogs = useCallback(async () => {
        if (!jobId) return;

        try {

            setDownloading(true);
            window.open(`/api/install/logs/${jobId}`, "_blank");
            setLogsDownloaded(true);
        } catch (e) {
            console.log("downloadLogs failed:", e);
        } finally {
            setDownloading(false);
        }
    }, [ jobId ]);

    return (
        <div className="absolute top-1/2 left-1/2 translate-x-[-50%] translate-y-[-50%]
        flex flex-col items-center justify-center gap-[18px]">
            <div className="flex flex-col items-center justify-center w-fit
                bg-[rgba(0,0,0,0.1)] px-[32px] py-[24px] rounded-[20px] gap-[24px]">
                <div className="flex flex-col items-center justify-center gap-[4px]">
                    <Text size="xxl" variant="bold">
                        {isFailedOnInstall ? t("install_page.install_failed.error_install_title")
                            : t("install_page.install_failed.error_server_activate_title")}
                    </Text>
                    <Text size="s" color="inactive" className="tracking-[-0.15px]">
                        {isSlowDiskSpeed ? t("install_page.install_failed.desc_slow_disk") : t("install_page.install_failed.desc")}
                    </Text>
                </div>
                {logsDownloaded ? (
                    <Progress value={progressBar} className="w-[545px]" classNameIndicator="bg-[#ff9d14]" />
                ) : (
                    <NoNetworkError
                        visible={networkError}
                        setVisible={setNetworkError}
                        triggerComponent={
                            <Progress value={progressBar} className="w-[545px]" classNameIndicator="bg-[#ff9d14]" />
                        }
                    />
                )}
                {isFailedOnInstall ? (
                    <>
                        {logsDownloaded ? (
                            <NoNetworkError
                                visible={networkError}
                                setVisible={setNetworkError}
                                triggerComponent={
                                    <Button
                                        className={`w-fit min-w-[219px] ${loading ? "pt-[9px] pb-[10px]" : "py-[6px]"}`}
                                        onClick={backToConfigure}
                                        disabled={loading}
                                    >
                                        {loading ?
                                            <Preloader size={16} />
                                            : t("install_page.install_failed.back_to_configure_button")
                                        }
                                    </Button>
                                }
                            />
                        ) : (
                            <CustomDialog showCloseButton={false} trigger={
                                <Button
                                    className={`w-fit min-w-[219px] ${loading ? "pt-[9px] pb-[10px]" : "py-[6px]"}`}
                                    disabled={loading}
                                >
                                    {loading ?
                                        <Preloader size={16} />
                                        : t("install_page.install_failed.back_to_configure_button")
                                    }
                                </Button>
                            } classNameContent="top-[246px] px-[20px] py-[20px]" content={
                                <>
                                    <div className="
                        w-[106px] h-[90px] download-logs-dialog-icon
                        absolute mt-[-50px] left-1/2 translate-x-[-50%]
                        " />
                                    <div className="flex flex-col justify-center items-center pt-[26px] gap-[16px]">
                                        <div className="flex flex-col justify-center items-center gap-[8px]">
                                            <Text variant="heavy" size="sm_heavy">
                                                {t("install_page.install_failed.download_logs_dialog.title")}
                                            </Text>
                                            <Text size="s" className="text-center tracking-[-0.15px]">
                                                {t("install_page.install_failed.download_logs_dialog.desc")}
                                            </Text>
                                        </div>
                                        <div className="w-full flex justify-between items-center">
                                            <DialogClose asChild>
                                                <Button
                                                    className="max-w-[124px]"
                                                    variant="secondary_cancel"
                                                    onClick={backToConfigure}
                                                >
                                                    {t("install_page.install_failed.download_logs_dialog.no_need_download_logs_button")}
                                                </Button>
                                            </DialogClose>
                                            <DialogClose asChild>
                                                <Button
                                                    className="max-w-[124px]"
                                                    onClick={() => {

                                                        downloadLogs()
                                                        backToConfigure()
                                                    }}
                                                >
                                                    {t("install_page.install_failed.download_logs_dialog.download_logs_button")}
                                                </Button>
                                            </DialogClose>
                                        </div>
                                    </div>
                                </>
                            } />
                        )}
                    </>
                ) : (
                    <NoNetworkError
                        visible={activateNetworkError}
                        setVisible={setActivateNetworkError}
                        triggerComponent={
                            <Button
                                className="w-fit min-w-[186px]"
                                onClick={tryActivateServerAgain}
                            >
                                {t("install_page.install_failed.retry_activate_server_button")}
                            </Button>
                        }
                    />
                )}
            </div>

            <Button
                className="w-fit"
                variant="text"
                onClick={downloadLogs}
                disabled={downloading}
            >
                {t("install_page.install_failed.download_logs_button")}
            </Button>
        </div>
    )
}

export default PageContentInstallFailed;