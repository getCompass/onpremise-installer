import { Text } from "@/components/ui/text.tsx";
import { useLangString } from "@/lib/getLangString.ts";

const PoweredByYandexCloud = () => {
    const t = useLangString();

    return (
        <div className="inline-flex items-center justify-center gap-[2px]">
            <Text className="tracking-[-0.12px]">{t("welcome_page.powered_by")}</Text>
            <div className="w-[100px] h-[14.5px] bg-center bg-cover bg-yandex-cloud bg-no-repeat shrink-0"></div>
        </div>
    );
}

export default PoweredByYandexCloud;