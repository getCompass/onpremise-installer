import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom';
import { Provider, useAtomValue } from "jotai";
import ErrorPage from "@/error-page.tsx";
import { useNavigatePage } from "@/components/hooks.ts";
import PageLayout from "@/pages/PageLayout.tsx";
import PageWelcome from "@/pages/PageWelcome.tsx";
import PageInstall from "@/pages/PageInstall.tsx";
import { isWelcomeSkippedState } from "@/api/_stores.ts";
import navigatePages from "@/lib/navigatePages.ts";

const Page = () => {
    const { activePage } = useNavigatePage();
    const isWelcomeSkipped = useAtomValue(isWelcomeSkippedState);
    const { navigateToNextPage } = navigatePages();

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
