import { type PropsWithChildren } from "react";

const PageLayout = ({ children }: PropsWithChildren) => {

    return (
        <div
            className="
        min-h-screen max-w-screen
        select-none
        bg-[#252732]
        font-lato_regular
      ">
            {children}
        </div>
    );
};

export default PageLayout;
