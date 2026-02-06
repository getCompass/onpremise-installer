import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom';
import { Provider, useAtomValue, useSetAtom } from "jotai";
import ErrorPage from "@/error-page.tsx";
import { useNavigatePage } from "@/components/hooks.ts";
import PageLayout from "@/pages/PageLayout.tsx";
import PageWelcome from "@/pages/PageWelcome.tsx";
import PageInstall from "@/pages/PageInstall.tsx";
import {
    isSlowDiskSpeedState,
    isWelcomeSkippedState,
    MIN_CPU_COUNT,
    MIN_DISK_SPACE_MB,
    MIN_RAM_MB,
    productTypeState,
    RECOMMENDED_DISK_SPACE_MB,
    serverSpecsAlertState
} from "@/api/_stores.ts";
import navigatePages from "@/lib/navigatePages.ts";
import { useAtom } from "jotai/index";
import { useEffect } from "react";

type ServerInfoResponseStruct = {
    success: boolean;
    cpu_cores: number;
    ram_mb: number;
    disk_mb: number;
    is_yandex_cloud_product: boolean;
};
const Page = () => {
    const { activePage } = useNavigatePage();
    const isWelcomeSkipped = useAtomValue(isWelcomeSkippedState);
    const { navigateToNextPage } = navigatePages();

    const [ serverSpecsAlert, setServerSpecsAlert ] = useAtom(serverSpecsAlertState);
    const setIsSlowDiskSpeed = useSetAtom(isSlowDiskSpeedState);
    const setProductType = useSetAtom(productTypeState);

    useEffect(() => {

        if (serverSpecsAlert === "unknown") {

            (async function checkServerSpecs() {

                const response = await fetch("/api/server/info");
                if (!response.ok) {
                    console.log(`Failed to get server info: ${response.status} ${response.statusText}`);
                    return;
                }
                const json = (await response.json()) as ServerInfoResponseStruct;
                if (!json.success) {
                    console.log("Failed to get server info");
                    return;
                }

                if (json.disk_mb >= RECOMMENDED_DISK_SPACE_MB) {
                    setIsSlowDiskSpeed(false);
                }

                (json.is_yandex_cloud_product) ? setProductType("yandex_cloud") : setProductType("default")

                if (json.cpu_cores < MIN_CPU_COUNT || json.ram_mb < MIN_RAM_MB || json.disk_mb < MIN_DISK_SPACE_MB) {

                    setServerSpecsAlert("visible");
                    return;
                }
            })();
        }
    }, [])

    switch (activePage) {
        case "welcome":
            if (isWelcomeSkipped) {

                navigateToNextPage();
                return <PageInstall />;
            }

            return <PageWelcome />;

        case "install":
            return <PageInstall />;

        default:
            return <PageWelcome />;
    }
};

const router = createBrowserRouter([
    {
        children: [
            {
                path: "*",
                element: (
                    <Navigate to="/install" replace />
                ),
            },
            {
                path: "/install",
                element: (
                    <PageLayout>
                        <Page />
                    </PageLayout>
                ),
            },
        ],
        errorElement: <ErrorPage />,
    },
]);

export default function App() {
    return (
        <Provider>
            <RouterProvider
                router={router}
            />
        </Provider>
    );
}
