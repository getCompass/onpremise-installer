import { useLangString } from "@/lib/getLangString.ts";
import { Text } from "@/components/ui/text.tsx";
import CompassWithYandexCloudLogo from "@/components/icons/CompassWithYandexCloudLogo.tsx";
import ButtonWithIcon from "@/components/ButtonWithIcon.tsx";
import { useMemo } from "react";
import { useNavigatePageContent } from "@/components/hooks.ts";
import PageContentInstallConfigure from "@/pages/install/PageContentInstallConfigure.tsx";
import CustomDialog from "@/components/CustomDialog.tsx";
import PageContentInstallInProgress from "@/pages/install/PageContentInstallInProgress.tsx";
import PageContentInstallSuccess from "@/pages/install/PageContentInstallSuccess.tsx";
import PageContentInstallFailed from "@/pages/install/PageContentInstallFailed.tsx";
import UnsavedChangesGuard from "@/components/UnsavedChangesGuard.tsx";
import useIsInstallDirty from "@/lib/useIsInstallDirty.ts";
import { useAtomValue } from "jotai";
import { jobIdState, productTypeState } from "@/api/_stores.ts";
import navigatePages from "@/lib/navigatePages.ts";
import CompassLogo from "@/components/icons/CompassLogo";

const Header = () => {

    const t = useLangString();
    const productType = useAtomValue(productTypeState)

    const docLink = useMemo(() => {
        if (productType == "yandex_cloud") {
            return "https://doc-onpremise.getcompass.ru/yandex-cloud.html"
        }
        return "https://doc-onpremise.getcompass.ru/fast-install.html";
    }, [productType]);

    const [installHeader, supportLink] = useMemo(() => {
        if (productType == "yandex_cloud") {
            return [t("install_page.header.yandex_title"), "https://t.me/getcompass_cloud"]
        }
        return [t("install_page.header.default_title"), "https://t.me/getcompass"]
    }, [productType]);

    const renderLinkDesc = () => {

        const [text, target] = useMemo(() => {
            if (productType == "yandex_cloud") {
                return [t("install_page.header.support_dialog.yandex_desc"), "support-cloud@getcompass.ru"]
            }
            return [t("install_page.header.support_dialog.default_desc"), "support@getcompass.ru"]
        }, [productType]);

        const i = text.indexOf(target);
        if (i === -1) return text;

        return (
            <>
                {text.slice(0, i)}
                <a
                    href="mailto:support-cloud@getcompass.ru"
                    target="_blank"
                    rel="noopener noreferrer"
                    className={`
                    text-[#009fe6] hover:text-[#0082bd] outline-none
                    `}
                >
                    {target}
                </a>
                {text.slice(i + target.length)}
            </>
        );
    };

    return (
        <div className="
          fixed top-0 left-0 right-0 z-49
          h-[68px]
          flex flex-row items-center justify-between gap-[24px]
          px-[48px] py-[16px]
          bg-[rgba(0,0,0,0.1)] backdrop-blur-[20px]"
        >
            <div className="flex flex-row justify-center items-center gap-[20px] min-w-0 flex-1">
                <div className="shrink-0">
                    {productType == "yandex_cloud" ? <CompassWithYandexCloudLogo /> : <CompassLogo />}
                </div>
                <Text size="m" className="truncate min-w-0 flex-1">{installHeader}</Text>
            </div>
            <div className="flex flex-row gap-[12px]">
                <CustomDialog trigger={
                    <ButtonWithIcon
                        icon={<div className="w-[16px] h-[16px] bg-support-icon" />}
                        text={t("install_page.header.support_title")} />
                } classNameContent="top-[246px] px-[24px]" content={
                    <>
                        <div className="
                        w-[106px] h-[90px] bg-support-dialog-icon
                        absolute mt-[-50px] left-1/2 translate-x-[-50%]
                        " />
                        <div className="flex flex-col justify-center items-center pt-[22px] gap-[20px]">
                            <div className="flex flex-col justify-center items-center gap-[8px]">
                                <Text variant="heavy" size="sm_heavy">
                                    {t("install_page.header.support_dialog.title")}
                                </Text>
                                <Text size="s" className="text-center tracking-[-0.15px]">
                                    {renderLinkDesc()}
                                </Text>
                            </div>
                            <div className="w-full px-[8px]">
                                <a
                                    href={supportLink}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="w-full"
                                >
                                    <ButtonWithIcon
                                        className="gap-[6px]"
                                        icon={
                                            <div className="w-[14px] h-[14px] bg-telegram-icon" />
                                        }
                                        text={t("install_page.header.support_dialog.button")}
                                        variant="dialog"
                                        size="dialog"
                                    />
                                </a>
                            </div>
                        </div>
                    </>
                } />
                <a
                    href={docLink}
                    target="_blank"
                    rel="noopener noreferrer"
                >
                    <ButtonWithIcon icon={<div className="w-[10px] h-[14px] bg-docs-icon" />}
                        text={t("install_page.header.documentation_title")} />
                </a>
            </div>
        </div>
    );
}

const PageInstall = () => {
    const { activePageContent } = useNavigatePageContent();
    const { navigateToNextPage } = navigatePages();
    const isDirty = useIsInstallDirty();
    const jobId = useAtomValue(jobIdState);

    const content = useMemo(() => {

        switch (activePageContent) {

            case "configure":

                if (jobId.length > 0) {

                    navigateToNextPage();
                    return <PageContentInstallInProgress />;
                }

                return <PageContentInstallConfigure />;

            case "install_in_progress":
                return <PageContentInstallInProgress />;

            case "install_success":
                return <PageContentInstallSuccess />;

            case "install_failed":
                return <PageContentInstallFailed />

            default:
                return <PageContentInstallConfigure />;
        }
    }, [activePageContent])

    return (
        <div className="flex flex-col h-screen w-screen overflow-hidden">
            <UnsavedChangesGuard active={isDirty} />
            <Header />
            <div className="h-full overflow-hidden">
                {content}
            </div>
        </div>
    );
}

export default PageInstall;