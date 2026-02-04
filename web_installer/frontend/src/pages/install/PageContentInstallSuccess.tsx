import { useLangString } from "@/lib/getLangString.ts";
import { Text } from "@/components/ui/text.tsx";
import { Button } from "@/components/ui/button.tsx";
import { useEffect, useState } from "react";
import { Input } from "@/components/ui/input.tsx";
import { cn } from "@/lib/utils.ts";
import { copyToClipboard } from "@/lib/copyToClipboard.ts";
import {
    INITIAL_JOB_STATUS_RESPONSE,
    installStartedAtState,
    jobIdState,
    jobStatusResponseState,
    progressBarState
} from "@/api/_stores.ts";
import { useSetAtom } from "jotai";
import type { AuthMethod } from "@/api/_types.ts";
import { useAtom } from "jotai/index";
import { useNavigatePageContent } from "@/components/hooks.ts";

type ResultResponseStruct = {
    success: boolean;
    status: "installed" | "not_found";
    data: ResultDataStruct;
}
type ResultDataStruct = {
    url?: string;
    auth_methods?: AuthMethod[];
    credentials?: {
        phone_number?: string;
        mail_login?: string;
        mail_password?: string;
        sso_login?: string;
    };
}
const PageContentInstallSuccess = () => {
    const t = useLangString();
    const [ jobId, setJobId ] = useAtom(jobIdState);
    const setInstallStartedAt = useSetAtom(installStartedAtState);
    const setProgressBar = useSetAtom(progressBarState);
    const setJobStatusResponse = useSetAtom(jobStatusResponseState);
    const [ data, setData ] = useState<ResultDataStruct>({});
    const { navigateToPageContent } = useNavigatePageContent();

    const [ showPassword, setShowPassword ] = useState(false);

    useEffect(() => {
        (async function getResult() {

            if (jobId.length < 1) {
                return;
            }

            const response = await fetch(`/api/install/result/${jobId}`);
            const json = (await response.json()) as ResultResponseStruct;
            if (json.success) {

                if (json.status === "installed") {
                    setData(json.data);
                    return;
                }

                if (json.status === "not_found") {

                    setJobId("");
                    setInstallStartedAt(0);
                    setJobStatusResponse(INITIAL_JOB_STATUS_RESPONSE);
                    setProgressBar(0);
                    navigateToPageContent("configure");
                    return;
                }
            }
        })();
    }, [ jobId ]);

    const InputItem = ({
        className, label, value
    }: { className?: string; label: string, value: string }) => {
        return (
            <div className={`flex flex-col gap-[6px] 
            bg-[rgba(0,0,0,0.1)] w-full px-[16px] pt-[8px] pb-[12px] ${className ?? ""}`}>
                <Text size="xs">{label}</Text>
                <Text size="sm" className="select-text">{value}</Text>
            </div>
        )
    }

    const ReadOnlyPassword = () => {

        const buttonBase = "w-[18px] h-[18px] cursor-pointer";

        return (
            <div className={cn(
                "flex flex-col gap-[6px]",
                "bg-[rgba(0,0,0,0.1)] w-full px-[16px] pt-[8px] pb-[12px]",
                !data.auth_methods?.includes("sso") ? "rounded-b-[12px]" : ""
            )}>
                <Text size="xs">{t("install_page.install_success.admin_mail_password_title")}</Text>
                <div className="flex justify-between select-text">
                    <Input
                        className="truncate"
                        type={showPassword ? "text" : "password"}
                        readOnly
                        value={data.credentials?.mail_password} />
                    <div className="flex gap-[8px]">
                        <div
                            className={cn(buttonBase,
                                showPassword ? "bg-password-visible-icon"
                                    : "bg-password-hidden-icon")}
                            onClick={() => setShowPassword((s) => !s)} />
                        <div
                            className={cn(buttonBase, "bg-copy-icon")}
                            onClick={() => copyToClipboard(data.credentials?.mail_password ?? "")} />
                    </div>
                </div>
            </div>
        )
    }

    return (
        <div className="absolute top-1/2 left-1/2 translate-x-[-50%] translate-y-[calc(-50%_+_68px)]">
            <div className="flex flex-col items-center justify-center w-[408px]
                bg-[rgba(0,0,0,0.1)] px-[24px] pt-[40px] pb-[24px] rounded-[20px] gap-[24px]">
                <div className="flex flex-col items-center justify-center">
                    <div className="w-[70px] h-[70px] bg-check-icon" />
                    <Text size="m_black" variant="black" color="white" className="mt-[12px] tracking-[-0.2px]">
                        {t("install_page.install_success.title")}
                    </Text>
                    <Text size="s" className="mt-[6px] tracking-[-0.15px] text-center max-w-[286px] select-text">
                        {(() => {
                            const desc = t("install_page.install_success.desc");
                            const [ before, after ] = desc.split("$DOMAIN");

                            return (
                                <>
                                    {before}
                                    <span className="font-lato-bold">{data.url ?? ""}</span>
                                    {after}
                                </>
                            );
                        })()}
                    </Text>
                </div>
                <div className="flex flex-col items-center justify-center gap-[1px] w-full">
                    {data.auth_methods?.includes("phone_number") && (
                        <InputItem
                            label={t("install_page.install_success.admin_phone_number_title")}
                            value={data.credentials?.phone_number ?? ""}
                            className={cn("truncate", "rounded-t-[12px]", data.auth_methods?.length === 1 ? "rounded-b-[12px]" : "")}
                        />
                    )}
                    {data.auth_methods?.includes("mail") && (
                        <>
                            <InputItem
                                label={t("install_page.install_success.admin_mail_login_title")}
                                value={data.credentials?.mail_login ?? ""}
                                className={cn("truncate", !data.auth_methods?.includes("phone_number") ? "rounded-t-[12px]" : "")}
                            />
                            <ReadOnlyPassword />
                        </>
                    )}
                    {data.auth_methods?.includes("sso") && (
                        <InputItem
                            label={t("install_page.install_success.admin_sso_login_title")}
                            value={data.credentials?.sso_login ?? ""}
                            className={cn("truncate", "rounded-b-[12px]", data.auth_methods?.length === 1 ? "rounded-t-[12px]" : "")}
                        />
                    )}
                </div>
                <a
                    href={`https://${data.url ?? ""}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="w-full"
                >
                    <Button>{t("install_page.install_success.button")}</Button>
                </a>
            </div>
        </div>
    )
}

export default PageContentInstallSuccess;