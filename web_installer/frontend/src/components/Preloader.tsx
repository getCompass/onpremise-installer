import { useMemo } from "react";

const Preloader = ({ size, variant = "default" }: {
    size: number,
    variant?: "default" | "label"
}) => {

    const img = useMemo(() => {

        switch (variant) {

            case "label":
                return "bg-preloader-label";

            default:
                return "bg-preloader";
        }
    }, [ variant ])

    return (
        <div
            className={`w-[${size}px] h-[${size}px] bg-no-repeat flex justify-center items-center animate-spin ${img}`}
        />
    )
}

export default Preloader;