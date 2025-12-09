import { Text } from "@/components/ui/text.tsx";
import { useLangString } from "@/lib/getLangString.ts";
import { Progress } from "@/components/ui/progress.tsx";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import useNavigatePages from "@/lib/navigatePages.ts";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import {
    activateServerStatusState,
    INITIAL_JOB_STATUS_RESPONSE,
    installStartedAtState,
    isSlowDiskSpeedState,
    jobIdState,
    jobStatusResponseState,
    progressBarState
} from "@/api/_stores.ts";
import { INSTALL_STEP_LIST, type StatusResponse } from "@/api/_types.ts";
import { useNavigatePageContent } from "@/components/hooks.ts";
import NoNetworkError from "@/components/NoNetworkError.tsx";
import dayjs from "dayjs";

type ActivateServerResponseStruct = { success: boolean };

const PageContentInstallInProgress = () => {
    const t = useLangString();
    const { navigateToNextPage } = useNavigatePages();
    const { navigateToPageContent } = useNavigatePageContent();
    const [ networkError, setNetworkError ] = useState(false);

    const [ progressBar, setProgressBar ] = useAtom(progressBarState);
    const [ jobStatusResponse, setJobStatusResponse ] = useAtom(jobStatusResponseState);
    const [ jobId, setJobId ] = useAtom(jobIdState);
    const [ installStartedAt, setInstallStartedAt ] = useAtom(installStartedAtState);
    const setActivateServerStatus = useSetAtom(activateServerStatusState);
    const isSlowDiskSpeed = useAtomValue(isSlowDiskSpeedState);
    const [ errorCount, setErrorCount ] = useState(0);
    const firstStepInstallTime = useMemo(() => {

        if (isSlowDiskSpeed) {
            return 20 * 60;
        }

        return 10 * 60;
    }, [ isSlowDiskSpeed ]);

    const clearToConfigure = useCallback(() => {
        startedRef.current = false;
        setJobId("");
        setInstallStartedAt(0);
        setJobStatusResponse(INITIAL_JOB_STATUS_RESPONSE);
        setProgressBar(0);
        navigateToPageContent("configure");
    }, [])

    // предотвращаем запуск второго цикла запросов
    const startedRef = useRef(false);

    useEffect(() => {
        if (!jobId) return;
        if (startedRef.current) return; // запрос уже идет
        startedRef.current = true;

        let stopped = false;

        const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

        const tick = async () => {
            // создаем контроллер, чтобы отменить запрос при размонтировании/смене jobId
            const controller = new AbortController();
            const { signal } = controller;

            // если эффект будет очищен до await - отменим fetch
            // вернем функцию, которая дернется при cleanup
            const cancel = () => controller.abort();

            try {
                const response = await fetch(`/api/install/status/${jobId}`, { signal });
                const json = (await response.json()) as StatusResponse;
                setJobStatusResponse(json);

                if (!json.success) {
                    setErrorCount((e) => e + 1);
                    return cancel;
                }

                // вычисляем прогресс по выполненным шагам
                const total = INSTALL_STEP_LIST.length || 1;
                const done = Math.min(json.completed_step_list?.length ?? 0, total);
                let percent = Math.round((done / total) * 100);

                // первый этап долгий - показываем "движущийся" прогресс, чтобы не было ощущения что все зависло
                if (done < 1) {
                    const now = dayjs().unix();

                    const elapsedTime = Math.max(0, now - installStartedAt);
                    const firstStepMaxPercent = 100 / total;

                    // прогресс внутри первого шага от 0 до 1
                    const progressInsideStep = Math.min(elapsedTime / firstStepInstallTime, 1);

                    // линейно размазываем до 25%
                    percent = Math.round(firstStepMaxPercent * progressInsideStep);
                }
                setProgressBar(percent);

                if (json.status === "not_found") {
                    stopped = true;
                    clearToConfigure();
                    return cancel;
                }

                if (json.status === "finished") {
                    stopped = true;
                    startedRef.current = false;
                    try {
                        const response = await fetch(`/api/install/activate_server`, { method: "POST" });
                        const json = (await response.json()) as ActivateServerResponseStruct;
                        if (json.success) {
                            setProgressBar(100);
                            setActivateServerStatus("success");
                            navigateToPageContent("install_success");
                            return cancel;
                        }
                        setActivateServerStatus("failed");
                        navigateToNextPage(false);
                    } catch {
                        setActivateServerStatus("failed");
                        navigateToNextPage(false);
                    }
                    return cancel;
                }

                if (json.status === "error") {
                    stopped = true;
                    startedRef.current = false;
                    navigateToNextPage(false);
                    return cancel;
                }
            } catch (e) {
                // игнорируем AbortError
                // @ts-expect-error
                if (e?.name !== "AbortError") {

                    setErrorCount((er) => er + 1)
                    setNetworkError(true);
                }
            }
            return cancel;
        };

        let lastCancel: (() => void) | undefined;

        (async function loop() {
            while (!stopped) {
                lastCancel = await tick();
                if (stopped) break;
                await sleep(2000);
            }
        })();

        return () => {
            stopped = true;
            startedRef.current = false;
            lastCancel?.();
        };
    }, [ jobId, installStartedAt ]);

    useEffect(() => {

        // пишем на всякий случай
        console.log(`Количество ошибок запроса status: ${errorCount}`)
    }, [ errorCount ]);

    return (
        <div className="absolute top-1/2 left-1/2 translate-x-[-50%] translate-y-[-50%]">
            <div className="flex flex-col items-center justify-center w-fit
                bg-[rgba(0,0,0,0.1)] px-[32px] py-[24px] rounded-[20px] gap-[24px]">
                <div className="flex flex-col items-center justify-center gap-[4px]">
                    <Text size="xxl" variant="bold">
                        {t(jobStatusResponse.completed_step_list.includes("create_team")
                            ? "install_page.install_in_progress.activate_title"
                            : "install_page.install_in_progress.install_title")}
                    </Text>
                    <Text size="s" color="inactive" className="tracking-[-0.15px]">
                        {isSlowDiskSpeed ? t("install_page.install_in_progress.desc_slow_disk") : t("install_page.install_in_progress.desc")}
                    </Text>
                </div>
                <NoNetworkError
                    visible={networkError}
                    setVisible={setNetworkError}
                    triggerComponent={
                        <Progress value={progressBar} className="w-[545px]" />
                    }
                />
            </div>
        </div>
    );
};

export default PageContentInstallInProgress;