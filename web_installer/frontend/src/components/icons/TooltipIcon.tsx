type TooltipIconProps = {
    className?: string;
};
const TooltipIcon = ({ className = "w-[16px] h-[16px]" }: TooltipIconProps) => {

    return (
        <div className={`${className} bg-cover bg-tooltip-icon`} />
    );
}

export default TooltipIcon;