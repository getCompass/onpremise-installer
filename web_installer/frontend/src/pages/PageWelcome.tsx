import CompassWelcomeLogo from "@/components/icons/CompassWelcomeLogo.tsx";
import { Button } from "@/components/ui/button.tsx";
import { useLangString } from "@/lib/getLangString.ts";
import PoweredByYandexCloud from "@/components/icons/PoweredByYandexCloud.tsx";
import useNavigatePages from "@/lib/navigatePages.ts";

const PageWelcome = () => {
    const t = useLangString();
    const { navigateToNextPage } = useNavigatePages();

    return (
        <div className="flex items-center justify-center min-h-screen max-w-screen">
            <div className="flex flex-col gap-[2px]">
                <div className="bg-[rgba(0,0,0,0.1)] pt-[34px] pb-[24px] px-[96px] rounded-t-[20px]">
                    <CompassWelcomeLogo />
                </div>
                <div className="bg-[rgba(0,0,0,0.1)] p-[24px] rounded-b-[20px]"
                     onClick={() => navigateToNextPage()}>
                    <Button>{t("welcome_page.button")}</Button>
                </div>
            </div>
            <div className="absolute bottom-[64px] left-1/2 -translate-x-1/2">
                <PoweredByYandexCloud />
            </div>
        </div>
    );
}

export default PageWelcome;