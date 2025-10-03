import {
    type ComponentProps,
    type Dispatch, type FocusEventHandler, forwardRef, Fragment,
    type InputHTMLAttributes,
    type ReactNode,
    type RefObject,
    type SetStateAction,
    useEffect,
    useRef,
    useState
} from "react";
import { useLangString } from "@/lib/getLangString.ts";
import { Text } from "@/components/ui/text.tsx";
import { Checkbox } from "@/components/ui/checkbox.tsx";
import { Label } from "@/components/ui/label.tsx";
import { Input } from "@/components/ui/input.tsx";
import { Textarea } from "@/components/ui/textarea.tsx";
import { Switch } from "@/components/ui/switch.tsx";
import { cn } from "@/lib/utils.ts";
import TooltipIcon from "@/components/icons/TooltipIcon.tsx";
import { Tooltip } from "@/components/ui/tooltip.tsx";
import StarIcon from "@/components/icons/StarIcon.tsx";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select.tsx";
import BlockStatus, { type blockFilledStatus } from "@/components/icons/BlockStatus.tsx";
import { Button } from "@/components/ui/button.tsx";
import WarningIcon from "@/components/icons/WarningIcon.tsx";
import CloseIcon from "@/components/icons/CloseIcon.tsx";
import {
    adminFormState,
    authFormState,
    autoCertsState,
    checkboxAccountDisablingMonitoringEnabledCheckedState,
    checkboxLdapUseSslCheckedState,
    domainFormState,
    jobIdState, MIN_CPU_COUNT, MIN_DISK_SPACE_MB, MIN_RAM_MB,
    selectedSsoProviderState,
    serverSpecsAlertState,
    switchEmailCheckedState,
    switchSmsAgentCheckedState,
    switchSsoCheckedState,
    switchTwilioCheckedState,
    switchVonageCheckedState
} from "@/api/_stores.ts";
import { useAtom, useSetAtom } from "jotai";
import useNavigatePages from "@/lib/navigatePages.ts";
import type {
    AdminFormState,
    AuthFormState,
    AuthMethod,
    DomainFormState,
    InvalidKeys,
    SectionKey,
    SmsProvider
} from "@/api/_types.ts";
import useTextFileDrop, { AllowedFileExtension, ProhibitedFileExtension } from "@/lib/useTextFileDrop.ts";
import Preloader from "@/components/Preloader.tsx";
import { normalizeBackendInvalidKeys } from "@/lib/functions.ts";
import ImagePreview from "@/components/ImagePreview.tsx";
import domainTooltipUrl from "@/img/domain-tooltip-image.png";
import NoNetworkError from "@/components/NoNetworkError.tsx";

/* =========================
   Свитчеры
   ========================= */

type AuthSettings = ReturnType<typeof useAuthSettings>;
const useAuthSettings = () => {
    const [ switchEmailChecked, setSwitchEmailChecked ] = useAtom(switchEmailCheckedState);
    const [ switchSsoChecked, setSwitchSsoChecked ] = useAtom(switchSsoCheckedState);
    const [ selectedSsoProvider, setSelectedSsoProvider ] = useAtom(selectedSsoProviderState);
    const [ switchSmsAgentChecked, setSwitchSmsAgentChecked ] = useAtom(switchSmsAgentCheckedState);
    const [ switchVonageChecked, setSwitchVonageChecked ] = useAtom(switchVonageCheckedState);
    const [ switchTwilioChecked, setSwitchTwilioChecked ] = useAtom(switchTwilioCheckedState);
    const [ checkboxLdapUseSslChecked, setCheckboxLdapUseSslChecked ] = useAtom(checkboxLdapUseSslCheckedState);
    const [ checkboxAccountDisablingMonitoringEnabledChecked, setCheckboxAccountDisablingMonitoringEnabledChecked ] = useAtom(checkboxAccountDisablingMonitoringEnabledCheckedState);

    return {
        switchEmailChecked, setSwitchEmailChecked,
        switchSsoChecked, setSwitchSsoChecked,
        selectedSsoProvider, setSelectedSsoProvider,
        switchSmsAgentChecked, setSwitchSmsAgentChecked,
        switchVonageChecked, setSwitchVonageChecked,
        switchTwilioChecked, setSwitchTwilioChecked,
        checkboxLdapUseSslChecked, setCheckboxLdapUseSslChecked,
        checkboxAccountDisablingMonitoringEnabledChecked, setCheckboxAccountDisablingMonitoringEnabledChecked
    };
};

/* =========================
   Общие компоненты
   ========================= */

const DashedLine = () => <div className="min-w-full border-t-[1px] border-dashed border-[rgba(255,255,255,0.1)]" />

type ConfirmBlockProps = {
    activeSection: SectionKey;
    onJump: (key: SectionKey) => void;
    onSubmit: () => void;
    statusDomain: blockFilledStatus;
    statusAuth: blockFilledStatus;
    statusAdmin: blockFilledStatus;
    setOfferAccepted: (v: boolean) => void;
    needShowErrorOfferAccepted: boolean;
    setNeedShowErrorOfferAccepted: (v: boolean) => void;
    loading: boolean;
    networkError: boolean;
    setNetworkError: (v: boolean) => void;
};
const ConfirmBlock = ({
    activeSection,
    onJump,
    onSubmit,
    statusDomain,
    statusAuth,
    statusAdmin,
    setOfferAccepted,
    needShowErrorOfferAccepted,
    setNeedShowErrorOfferAccepted,
    loading,
    networkError,
    setNetworkError,
}: ConfirmBlockProps) => {
    const t = useLangString();
    const itemBase =
        "bg-[rgba(0,0,0,0.1)] w-full px-[16px] py-[12px] flex justify-between items-center cursor-pointer";

    const renderOfferDesc = () => {
        const text = t("install_page.configure.confirm_block.offer_desc");
        const target_privacy = "политики конфиденциальности";
        const target_offer = "публичной оферты";
        const i_privacy = text.indexOf(target_privacy);
        const i_offer = text.indexOf(target_offer);
        if (i_privacy === -1 || i_offer === -1) return text;

        return (
            <>
                {text.slice(0, i_privacy)}
                <a
                    href="https://getcompass.ru/privacy.pdf"
                    target="_blank"
                    rel="noopener noreferrer"
                    className={cn(
                        "underline underline-offset-[3px] outline-none transition-opacity",
                        needShowErrorOfferAccepted ? "decoration-[#ff4f47] hover:text-[#ff271f] hover:decoration-[#ff271f]"
                            : "decoration-[rgba(255,255,255,0.3)] hover:text-[rgba(255,255,255,0.8)] hover:decoration-[rgba(255,255,255,0.8)]"
                    )}
                    // чтобы клик по ссылке не переключал чекбокс/label
                    onClick={(e) => e.stopPropagation()}
                    onMouseDown={(e) => e.stopPropagation()}
                >
                    {target_privacy}
                </a>
                {text.slice(i_privacy + target_privacy.length, i_offer)}
                <a
                    href="https://getcompass.ru/docs/yandex-cloud/offer.pdf"
                    target="_blank"
                    rel="noopener noreferrer"
                    className={cn(
                        "underline underline-offset-[3px] outline-none transition-opacity",
                        needShowErrorOfferAccepted ? "decoration-[#ff4f47] hover:text-[#ff271f] hover:decoration-[#ff271f]"
                            : "decoration-[rgba(255,255,255,0.3)] hover:text-[rgba(255,255,255,0.8)] hover:decoration-[rgba(255,255,255,0.8)]"
                    )}
                    // чтобы клик по ссылке не переключал чекбокс/label
                    onClick={(e) => e.stopPropagation()}
                    onMouseDown={(e) => e.stopPropagation()}
                >
                    {target_offer}
                </a>
                {text.slice(i_offer + target_offer.length)}
            </>
        );
    };

    const Item = ({ k, label, status }: { k: SectionKey; label: string; status: blockFilledStatus }) => {
        const active = activeSection === k;
        return (
            <div
                className={cn(itemBase, k === "domain" ? "rounded-t-[12px]" : "")}
                onClick={() => onJump(k)}
                role="button"
                aria-current={active ? "true" : undefined}
            >
                <Text size="sm" className="tracking-[-0.15px]" {...(!active ? { color: "inactive" } : {})}>
                    {label}
                </Text>
                <BlockStatus status={status} />
            </div>
        );
    };

    return (
        <div className="flex flex-col gap-[1px] w-[244px]">
            <Item k="domain" label={t("install_page.configure.confirm_block.domain_title")} status={statusDomain} />
            <Item k="auth" label={t("install_page.configure.confirm_block.auth_title")} status={statusAuth} />
            <Item k="admin" label={t("install_page.configure.confirm_block.admin_title")} status={statusAdmin} />
            <div className={"bg-[rgba(0,0,0,0.1)] w-full p-[16px] rounded-b-[12px] flex flex-col gap-[16px]"}>
                <div className="flex items-start justify-start gap-[8px]">
                    <Checkbox
                        id="accept-offer"
                        className={needShowErrorOfferAccepted ? "border-[#ff4f47]" : ""}
                        onCheckedChange={(checked) => {
                            setOfferAccepted(Boolean(checked))
                            if (needShowErrorOfferAccepted) {
                                setNeedShowErrorOfferAccepted(false)
                            }
                        }}
                    />
                    <Label
                        htmlFor="accept-offer"
                        className={cn(
                            "cursor-pointer text-[11px] leading-[15px]",
                            needShowErrorOfferAccepted ? "text-[#ff4f47]" : "text-[rgba(255,255,255,0.3)]")}
                    >
                        {renderOfferDesc()}
                    </Label>
                </div>
                <NoNetworkError
                    visible={networkError}
                    setVisible={setNetworkError}
                    triggerComponent={
                        <Button className={loading ? "pt-[9px] pb-[10px]" : "py-[6px]"} onClick={onSubmit}
                                disabled={loading}>
                            {loading ? (
                                <Preloader size={16} />
                            ) : t("install_page.configure.confirm_block.install_button")}
                        </Button>
                    }
                />
            </div>
        </div>
    );
}

type SubTitleBlockProps = {
    label: string;
    className?: string;
    tooltip?: ReactNode;
};
const SubTitleBlock = ({ label, className, tooltip }: SubTitleBlockProps) => (
    <div className={cn("bg-[rgba(0,0,0,0.1)] w-full px-[16px] pt-[12px] pb-[8px]", className)}>
        <Text size="s" className="tracking-[-0.15px]">
            {label}
            {tooltip}
        </Text>
    </div>
);

type LinkListProps = {
    className?: string;
    linkList: { label: string; link: string }[];
}
const LinkList = ({ className, linkList }: LinkListProps) => {

    return (
        <div className={cn("flex flex-col gap-[0px]", className)}>
            {linkList.map(({ label, link }) => (
                <div className="flex items-center">
                    <div className="px-[7px] py-[6px]">
                        <div className="w-[5px] h-[5px] rounded-full bg-[rgba(255,255,255,0.8)]" />
                    </div>
                    <a
                        href={link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="w-full"
                    >
                        <Text size="tooltip" color="link" className="hover:text-[#0082bd]">{label}</Text>
                    </a>
                </div>
            ))}
        </div>
    );
}

/* =========================
   Инпуты
   ========================= */

const isValidEmail = (mail: string) => {
    const v = mail.trim();
    return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v);
};

type InputBlockProps = {
    label: string;
    placeholder: string;
    className?: string;
    tooltip?: ReactNode;
    requiredField?: boolean;

    name: string;
    value: string;
    onChange: (v: string) => void;
    type?: InputHTMLAttributes<HTMLInputElement>["type"];
    inputProps?: InputHTMLAttributes<HTMLInputElement>;

    invalid?: boolean;

    labelBlock?: ReactNode;

    maxLength?: number;
}
const InputBlock = ({
    label, placeholder, className, tooltip, requiredField,
    name, value, onChange, type = "text", inputProps, invalid,
    labelBlock, maxLength = 1000
}: InputBlockProps) => {

    const [ showPassword, setShowPassword ] = useState(false);

    return (
        <div
            className={cn("flex flex-col gap-[6px] bg-[rgba(0,0,0,0.1)] w-full px-[16px] pt-[8px] pb-[12px]", className)}
            data-invalid={invalid || undefined}
        >
            {labelBlock ? (
                labelBlock
            ) : (
                <div className="inline-flex">
                    <Text size="xs" color={invalid ? "error" : "default"}>
                        {label}
                    </Text>
                    {requiredField && (
                        <StarIcon className={invalid ? "text-[#ff4f47]" : "text-[rgba(255,255,255,0.8)]"} />
                    )}
                    {tooltip}
                </div>
            )}
            {type === "password" ? (
                <div className="flex justify-between select-text">
                    <Input
                        name={name}
                        value={value}
                        onChange={(e) => onChange(e.target.value)}
                        placeholder={placeholder}
                        type={showPassword ? "text" : "password"}
                        aria-invalid={invalid || undefined}
                        maxLength={maxLength}
                        {...inputProps}
                    />
                    <div
                        className={cn("w-[18px] h-[18px] cursor-pointer select-none",
                            showPassword ? "bg-password-visible-icon"
                                : "bg-password-hidden-icon")}
                        onClick={() => setShowPassword((s) => !s)} />
                </div>
            ) : (
                <Input
                    name={name}
                    value={value}
                    onChange={(e) => onChange(e.target.value)}
                    placeholder={placeholder}
                    type={type}
                    aria-invalid={invalid || undefined}
                    maxLength={maxLength}
                    min={type === "number" ? 1 : undefined}
                    onWheel={(e) => {
                        if (type === "number") {
                            e.currentTarget.blur(); // убираем фокус, чтобы скролл не влиял
                        }
                    }}
                    onKeyDown={(e) => {
                        if (type === "number" && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
                            e.preventDefault(); // блокируем стрелки
                        }
                    }}
                    {...inputProps}
                />
            )}
        </div>
    );
}

type SelectorBlockProps = {
    label: string;
    className?: string;
    tooltip?: ReactNode;

    name: string;
    value: string;
    onChange: (v: string) => void;
    values: { key: string; label: string }[];
    defaultValue: string;

    invalid?: boolean;
};
const SelectorBlock = ({
    label, className, tooltip,
    name, value, onChange, values, invalid, defaultValue
}: SelectorBlockProps) => (
    <div
        className={cn("flex flex-col gap-[6px] bg-[rgba(0,0,0,0.1)] w-full px-[16px] pt-[8px] pb-[12px]", className)}
        data-invalid={invalid || undefined}
    >
        <Text size="xs" color={invalid ? "error" : "default"}>
            {label}
            {tooltip}
        </Text>
        <input type="hidden" name={name} value={value} readOnly />
        <Select value={value} onValueChange={onChange} defaultValue={defaultValue}>
            <SelectTrigger
                aria-invalid={invalid || undefined}
            >
                <SelectValue />
            </SelectTrigger>
            <SelectContent align="center">
                {values.map(({ key, label }) => (
                    <SelectItem key={key} value={key}>
                        {label}
                    </SelectItem>
                ))}
            </SelectContent>
        </Select>
    </div>
)

type AuthSwitcherBlockProps = {
    id: string;
    text: string;
    tooltip?: ReactNode;
    checked: boolean;
    onCheckedChange: (value: boolean) => void;
    clearInvalidKey: (k: string) => void;
}
const AuthSwitcherBlock = ({
    id,
    text,
    tooltip,
    checked,
    onCheckedChange,
    clearInvalidKey
}: AuthSwitcherBlockProps) => {

    const handleChange = (value: boolean) => {

        clearInvalidKey("auth.auth_methods");
        onCheckedChange(value);
        switch (id) {

            case "switch-auth-mail":
                [
                    "auth.smtp_host",
                    "auth.smtp_port",
                    "auth.smtp_user",
                    "auth.smtp_pass",
                    "auth.smtp_encryption",
                    "auth.smtp_from",
                    "admin.root_user_mail",
                    "admin.root_user_pass"
                ].forEach(key => clearInvalidKey(key))
                break;

            case "switch-auth-sso":
                [
                    "auth.sso_protocol",
                    "auth.sso_compass_mapping_name",
                    "auth.sso_compass_mapping_avatar",
                    "auth.sso_compass_mapping_badge",
                    "auth.sso_compass_mapping_role",
                    "auth.sso_compass_mapping_bio",
                    "auth.oidc_client_id",
                    "auth.oidc_client_secret",
                    "auth.oidc_oidc_provider_metadata_link",
                    "auth.oidc_attribution_mapping_mail",
                    "auth.oidc_attribution_mapping_phone_number",
                    "auth.ldap_server_host",
                    "auth.ldap_server_port",
                    "auth.ldap_use_ssl",
                    "auth.ldap_require_cert_strategy",
                    "auth.ldap_user_search_base",
                    "auth.ldap_user_unique_attribute",
                    "auth.ldap_user_search_filter",
                    "auth.ldap_user_search_account_dn",
                    "auth.ldap_user_search_account_password",
                    "auth.ldap_account_disabling_monitoring_enabled",
                    "admin.root_user_sso_login",
                ].forEach(key => clearInvalidKey(key))
                break;

            case "switch-auth-sms-agent":
                [
                    "auth.sms_agent_app_name",
                    "auth.sms_agent_login",
                    "auth.sms_agent_password",
                    "admin.root_user_phone",
                ].forEach(key => clearInvalidKey(key))
                break;

            case "switch-auth-vonage":
                [
                    "auth.vonage_app_name",
                    "auth.vonage_api_key",
                    "auth.vonage_api_secret",
                    "admin.root_user_phone",
                ].forEach(key => clearInvalidKey(key))
                break;

            case "switch-auth-twilio":
                [
                    "auth.twilio_app_name",
                    "auth.twilio_account_sid",
                    "auth.twilio_account_auth_token",
                    "admin.root_user_phone",
                ].forEach(key => clearInvalidKey(key))
                break;
            default:
                break;
        }
    };

    return (
        <div
            className={`flex items-center justify-between
                bg-[rgba(0,0,0,0.1)] ${checked ? "rounded-t-[12px]" : "rounded-[12px]"} w-full px-[16px] pt-[11px] pb-[10px]`}>
            <Text variant="bold" size="s" className="tracking-[-0.15px] inline-flex">
                {text}
                {tooltip}
            </Text>
            <Switch id={id} checked={checked} onCheckedChange={handleChange} />
        </div>
    )
}

/* =========================
   Блок домена
   ========================= */

const isValidDomain = (raw: string) => {
    const v = raw.trim();
    // та же логика, что и в pattern у инпута
    const re = /^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
    // не допускаем ведущую/замыкающую точку и двойные точки
    if (!re.test(v)) return false;
    return !(v.startsWith(".") || v.endsWith(".") || v.includes(".."));
};

const readTextFile = (file: File): Promise<string> =>
    new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onerror = () => reject(reader.error);
        reader.onload = () => resolve(String(reader.result ?? ""));
        reader.readAsText(file);
    });

type FileUploadLinkProps = {
    label: string;
    accept?: string;
    onText: (text: string, file: File) => void;
    className?: string;
    maxBytes?: number;
    nameAllow?: RegExp;
    onError?: (msg: string) => void;
};

const FileUploadLink = ({
    label,
    accept,
    onText,
    className,
    maxBytes = 10_000_000,
    nameAllow,
    onError,
}: FileUploadLinkProps) => {
    const t = useLangString();
    const inputRef = useRef<HTMLInputElement>(null);

    const handleError = (msgKey: string) => {
        onError?.(t(msgKey));
    };

    return (
        <>
            <input
                ref={inputRef}
                type="file"
                accept={accept}
                style={{ display: "none" }}
                onChange={async (e) => {
                    const file = e.currentTarget.files?.[0];
                    try {
                        if (!file) return;

                        const looksText =
                            file.type.startsWith("text/") ||
                            AllowedFileExtension.test(file.name);
                        const executedFiles = ProhibitedFileExtension.test(file.name);

                        const allowedByName = nameAllow ? nameAllow.test(file.name) : true;

                        if (!looksText || !allowedByName || executedFiles) {
                            handleError("install_page.configure.domain_block.ssl_upload_file_error_extension");
                            return;
                        }
                        if (file.size > maxBytes) {
                            handleError("install_page.configure.domain_block.ssl_upload_file_error_size");
                            return;
                        }

                        try {
                            const text = await readTextFile(file);
                            onText(text, file);
                        } catch {
                            handleError("install_page.configure.domain_block.ssl_upload_file_error_general");
                        }
                    } finally {
                        // сбрасываем value, чтобы можно было выбрать тот же файл повторно
                        if (e.currentTarget !== null) e.currentTarget.value = "";
                    }
                }}
            />
            <Text
                role="button"
                tabIndex={-1}
                className={cn("text-[#006be0] cursor-pointer select-none", className)}
                size="xs"
                onClick={() => inputRef.current?.click()}
                onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        inputRef.current?.click();
                    }
                }}
            >
                {label}
            </Text>
        </>
    );
};

type Props = ComponentProps<typeof Textarea> & {
    label: string;
    tooltipText: string;
    onDropText: (text: string, file: File) => void;
    classNameContainer?: string;
    invalidKey: string;
    invalidKeys: InvalidKeys;
    markInvalidKey: (k: string) => void;
    isError: boolean;
};

export const DroppableTextarea = ({
    label,
    tooltipText,
    onDropText,
    className,
    classNameContainer,
    invalidKey,
    invalidKeys,
    markInvalidKey,
    isError,
    ...rest
}: Props) => {
    const t = useLangString();
    const { isOver, error, dropProps, setError } = useTextFileDrop({ onText: onDropText });
    const wrapperRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (error !== null) {
            markInvalidKey(invalidKey);
        }
    }, [ error ]);

    useEffect(() => {
        if (error !== null && !invalidKeys.has(invalidKey)) {
            setError(null);
        }
    }, [ invalidKeys ]);

    return (
        <div ref={wrapperRef} className="relative w-full" {...dropProps}>
            <div
                className={cn(
                    "flex flex-col gap-[6px] bg-[rgba(0,0,0,0.1)] w-full px-[16px] pt-[8px] pb-[12px]",
                    classNameContainer
                )}>
                <div className="flex items-center justify-between">
                    <Text size="xs" color={isError ? "error" : "default"}>
                        {label}
                        <Tooltip classNameContent="max-w-[284px]" side="right"
                                 trigger={<TooltipIcon className="w-[14px] h-[14px] ml-[4px]" />}>
                            <Text size="tooltip" className="whitespace-pre-line">
                                {tooltipText}
                            </Text>
                        </Tooltip>
                    </Text>
                    <FileUploadLink
                        label={t("install_page.configure.domain_block.ssl_upload_button")}
                        accept=".txt,.log,.pem,.crt,.cer,.key,.cfg,.conf,.cnf"
                        onText={(text, file) => onDropText(text, file)}
                        onError={setError}
                    />
                </div>
                <div className="relative w-full">
                    <Tooltip
                        classNameContent="max-w-[203px]"
                        classNameTrigger="top-[13px]"
                        open={error !== null && invalidKeys.has(invalidKey)}
                        side="left"
                        sideOffset={16}
                    >
                        <Text size="s">
                            {error}
                        </Text>
                    </Tooltip>
                    <Textarea
                        {...rest}
                        className={cn(
                            "resize-none whitespace-pre-wrap overflow-x-hidden max-w-[800px] transition-colors",
                            "w-full",
                            className
                        )}
                    />

                    {/* оверлей заглушка */}
                    {isOver && (
                        <div
                            className="
            absolute inset-0 flex items-center justify-center
            bg-[#21232d] font-lato-regular text-[rgba(255,255,255,0.5)] text-[15px] leading-[21px]
            rounded-[5px] pointer-events-none border-[1px] border-dashed border-[rgba(255,255,255,0.2)]
          "
                        >
                            {t("install_page.configure.domain_block.ssl_upload_file_placeholder")}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

type DomainBlockProps = {
    form: DomainFormState;
    setForm: Dispatch<SetStateAction<DomainFormState>>;
    autoCerts: boolean;
    setAutoCerts: (v: boolean) => void;
    invalidKeys: InvalidKeys;
    clearInvalidKey: (k: string) => void;
    markInvalidKey: (k: string) => void;
};
const DomainBlock = forwardRef<HTMLDivElement, DomainBlockProps>(
    ({ form, setForm, autoCerts, setAutoCerts, invalidKeys, clearInvalidKey, markInvalidKey }, ref) => {
        const t = useLangString();
        const [ host, setHost ] = useState<string>("");
        const [ domainIp, setDomainIp ] = useState<string>("");
        const [ domainWarningVisible, setDomainWarningVisible ] = useState(false);
        const [ domainWarningText, setDomainWarningText ] = useState(t("install_page.configure.domain_block.domain_check_default_error"));
        const [ domainCheckLoading, setDomainCheckLoading ] = useState(false);

        useEffect(() => {
            if (typeof window !== "undefined") {
                setHost(window.location.hostname);
            }
        }, []);

        const blockInvalid = hasAny(invalidKeys, [
            "domain.domain",
            ...(autoCerts ? [] : [ "domain.cert", "domain.private_key" ])
        ]);

        return (
            <div className="flex flex-col items-start justify-start gap-[31px] w-full">
                <div className="flex flex-col items-start justify-start gap-[12px] px-[8px]">
                    <div ref={ref} id="section-domain" />
                    <Text variant="bold" size="xl" className="tracking-[-0.15px]">
                        {t("install_page.configure.domain_block.title")}
                    </Text>
                    <Text className="tracking-[-0.15px] whitespace-pre-line select-text">
                        {(() => {
                            const desc = t("install_page.configure.domain_block.desc");
                            const [ before, after ] = desc.split("$IP");

                            return (
                                <>
                                    {before}
                                    <span className="font-lato-bold text-[#ff9d14]">{host}</span>
                                    {after}
                                </>
                            );
                        })()}
                    </Text>
                    <div className="flex gap-[8px] items-center justify-start">
                        <Checkbox
                            id="ssl-certs"
                            checked={autoCerts}
                            onCheckedChange={(checked) => {
                                setAutoCerts(Boolean(checked))
                                clearInvalidKey("domain.cert");
                                clearInvalidKey("domain.private_key");
                            }}
                        />
                        <div className="flex items-center justify-start gap-x-[4px]">
                            <Label htmlFor="ssl-certs" className="cursor-pointer">
                                {t("install_page.configure.domain_block.checkbox")}
                            </Label>
                            <Tooltip classNameContent="max-w-[386px]" side="right" trigger={<TooltipIcon />}>
                                <Text size="tooltip" className="whitespace-pre-line">
                                    {t("install_page.hints.lets_encrypt_checkbox")}
                                </Text>
                            </Tooltip>
                        </div>
                    </div>
                </div>

                <div className="relative w-full">
                    <div
                        className={cn(
                            "flex flex-col gap-[1px] w-full border-[1px] rounded-[12px]",
                            domainWarningVisible ? "border-[#ff9d14]" : (blockInvalid ? "border-[#ff4f47]" : "border-transparent")
                        )}
                    >
                        <InputBlock
                            label={t("install_page.configure.domain_block.domain_input_title")}
                            labelBlock={
                                <div className="inline-flex items-center gap-[8px]">
                                    <div className="inline-flex">
                                        <Text
                                            size="xs"
                                            color={domainWarningVisible ? "warning" : (invalidKeys.has("domain.domain") ? "error" : "default")}
                                        >
                                            {t("install_page.configure.domain_block.domain_input_title")}
                                            <Tooltip side="right"
                                                     trigger={<TooltipIcon className="w-[14px] h-[14px] ml-[4px]" />}>
                                                <div
                                                    className="flex flex-col items-start justify-center gap-[12px] max-w-[596px]">
                                                    <Text size="tooltip" className="whitespace-pre-line">
                                                        {t("install_page.hints.domain_input_pt1")}
                                                    </Text>
                                                    <ImagePreview
                                                        triggerClassName="w-[596px] h-[124px] rounded-[8px] bg-cover bg-domain-tooltip-image"
                                                        url={domainTooltipUrl}
                                                    />
                                                    <Text size="tooltip">
                                                        {t("install_page.hints.domain_input_pt2")}
                                                    </Text>
                                                </div>
                                            </Tooltip>
                                        </Text>
                                    </div>
                                    {domainCheckLoading && (
                                        <Preloader size={14} variant="label" />
                                    )}
                                </div>
                            }
                            placeholder={t("install_page.configure.domain_block.domain_input_placeholder")}
                            className="rounded-t-[12px]"
                            name="domain"
                            value={form.domain}
                            onChange={(v) => {
                                setForm((s) => ({ ...s, domain: v }));
                                clearInvalidKey("domain.domain");
                                setDomainWarningVisible(false);
                            }}
                            inputProps={{
                                pattern: "^[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$",
                                onBlur: async (e) => {
                                    const val = e.currentTarget.value.trim();

                                    if (val.length < 1) {
                                        return;
                                    }

                                    if (!isValidDomain(val)) {
                                        markInvalidKey("domain.domain");
                                        return;
                                    }

                                    clearInvalidKey("domain.domain");

                                    // показываем лоадер на время запроса
                                    setDomainCheckLoading(true);
                                    try {
                                        const response = await fetch("/api/domain/resolve", {
                                            method: "POST",
                                            headers: { "Content-Type": "application/json" },
                                            body: JSON.stringify({ domain: val })
                                        });

                                        if (!response.ok) {

                                            setDomainWarningText(t("install_page.configure.domain_block.domain_check_default_error"));
                                            setDomainWarningVisible(true);
                                            return;
                                        }

                                        const data = await response.json() as {
                                            success: boolean;
                                            domain: string;
                                            system_dns: string[];
                                            google_dns: string[];
                                        };
                                        if (!data.success) {

                                            setDomainWarningText(t("install_page.configure.domain_block.domain_check_default_error"));
                                            setDomainWarningVisible(true);
                                            return;
                                        }
                                        setDomainIp(data.google_dns.length > 0 ? data.google_dns[0] : (data.system_dns.length > 0 ? data.google_dns[0] : ""));

                                        if (data.google_dns.length < 1 && data.system_dns.length < 1) {

                                            setDomainWarningText(t("install_page.configure.domain_block.domain_check_default_error"));
                                            setDomainWarningVisible(true);
                                            return;
                                        }

                                        if (!data.google_dns.includes(host) && !data.system_dns.includes(host)) {

                                            setDomainWarningText(t("install_page.configure.domain_block.domain_check_ip_error"));
                                            setDomainWarningVisible(true);
                                            return;
                                        }
                                        setDomainWarningVisible(false);
                                    } catch {
                                        setDomainWarningText(t("install_page.configure.domain_block.domain_check_default_error"));
                                        setDomainWarningVisible(true);
                                    } finally {
                                        setDomainCheckLoading(false);
                                    }
                                }
                            }}
                            invalid={invalidKeys.has("domain.domain")}
                        />
                        {autoCerts ? (
                            <div
                                className="flex flex-col gap-[6px] bg-[rgba(0,0,0,0.1)] rounded-b-[12px] w-full px-[16px] pt-[8px] pb-[12px]">
                                <Text size="xs">
                                    {t("install_page.configure.domain_block.ssl_cert_input_title")}
                                    <Tooltip classNameContent="max-w-[284px]" side="right"
                                             trigger={<TooltipIcon className="w-[14px] h-[14px] ml-[4px]" />}>
                                        <Text size="tooltip" className="whitespace-pre-line">
                                            {t("install_page.hints.ssl_certificate_input")}
                                        </Text>
                                    </Tooltip>
                                </Text>
                                <Text
                                    color="inactive">{t("install_page.configure.domain_block.checkbox_checked_desc")}</Text>
                                <input type="hidden" name="cert" value="" />
                                <input type="hidden" name="private_key" value="" />
                            </div>
                        ) : (
                            <>
                                <DroppableTextarea
                                    id="ssl_cert"
                                    label={t("install_page.configure.domain_block.ssl_cert_input_title")}
                                    tooltipText={t("install_page.hints.ssl_certificate_input")}
                                    className="resize-none whitespace-pre-wrap overflow-x-hidden max-w-[800px]"
                                    rows={4}
                                    placeholder={t("install_page.configure.domain_block.ssl_cert_input_placeholder")}
                                    value={form.cert}
                                    onChange={(e) => {
                                        setForm((s) => ({ ...s, cert: (e.target.value ?? "").trim() }));
                                        clearInvalidKey("domain.cert");
                                    }}
                                    aria-invalid={invalidKeys.has("domain.cert") || undefined}
                                    maxLength={20000}
                                    onDropText={(text) => {
                                        setForm((s) => ({ ...s, cert: text.trim() }));
                                        clearInvalidKey("domain.cert");
                                    }}
                                    invalidKey="domain.cert"
                                    invalidKeys={invalidKeys}
                                    markInvalidKey={markInvalidKey}
                                    isError={invalidKeys.has("domain.cert")}
                                />
                                <DroppableTextarea
                                    id="ssl_private_key"
                                    label={t("install_page.configure.domain_block.ssl_private_key_input_title")}
                                    tooltipText={t("install_page.hints.private_key_input")}
                                    className="resize-none whitespace-pre-wrap overflow-x-hidden max-w-[800px]"
                                    classNameContainer="rounded-b-[12px]"
                                    rows={4}
                                    placeholder={t("install_page.configure.domain_block.ssl_private_key_input_placeholder")}
                                    value={form.private_key}
                                    onChange={(e) => {
                                        setForm((s) => ({ ...s, private_key: (e.target.value ?? "").trim() }));
                                        clearInvalidKey("domain.private_key");
                                    }}
                                    aria-invalid={invalidKeys.has("domain.private_key") || undefined}
                                    maxLength={20000}
                                    onDropText={(text) => {
                                        setForm((s) => ({ ...s, private_key: text.trim() }));
                                        clearInvalidKey("domain.private_key");
                                    }}
                                    invalidKey="domain.private_key"
                                    invalidKeys={invalidKeys}
                                    markInvalidKey={markInvalidKey}
                                    isError={invalidKeys.has("domain.private_key")}
                                />
                            </>
                        )}
                    </div>
                    <Tooltip
                        side="left"
                        classNameContent="max-w-[203px] pb-[12px]"
                        classNameTrigger="top-[43px]"
                        open={domainWarningVisible}
                        sideOffset={-1}
                    >
                        <div className="flex flex-col gap-[16px]">
                            <Text size="s" className="whitespace-pre-line">
                                {domainWarningText
                                    .split(/(\$SERVER_IP|\$DOMAIN_IP)/g)
                                    .map((part, i) => {
                                        if (part === "$SERVER_IP") {
                                            return (
                                                <span key={i} className="font-lato-bold">{host}</span>
                                            );
                                        }
                                        if (part === "$DOMAIN_IP") {
                                            return (
                                                <span key={i} className="font-lato-bold">{domainIp}</span>
                                            );
                                        }
                                        return <Fragment key={i}>{part}</Fragment>;
                                    })}
                            </Text>
                            <Button onClick={() => setDomainWarningVisible(false)}>
                                {t("install_page.configure.domain_block.domain_check_close_button")}
                            </Button>
                        </div>
                    </Tooltip>
                </div>
            </div>
        )
    }
)
DomainBlock.displayName = "DomainBlock";

/* =========================
   Блок авторизации
   ========================= */

type AuthBlockProps = AuthSettings & {
    form: AuthFormState;
    setForm: Dispatch<SetStateAction<AuthFormState>>;
    invalidKeys: InvalidKeys;
    markInvalidKey: (k: string) => void;
    clearInvalidKey: (k: string) => void;
};
const AuthBlock = forwardRef<HTMLDivElement, AuthBlockProps>((props, ref) => {
    const t = useLangString();
    const {
        form, setForm, invalidKeys,
        switchEmailChecked, setSwitchEmailChecked,
        switchSsoChecked, setSwitchSsoChecked,
        selectedSsoProvider, setSelectedSsoProvider,
        switchSmsAgentChecked, setSwitchSmsAgentChecked,
        switchVonageChecked, setSwitchVonageChecked,
        switchTwilioChecked, setSwitchTwilioChecked,
        checkboxLdapUseSslChecked, setCheckboxLdapUseSslChecked,
        checkboxAccountDisablingMonitoringEnabledChecked, setCheckboxAccountDisablingMonitoringEnabledChecked,
        markInvalidKey, clearInvalidKey
    } = props;

    // поддерживаем протокол sso в стейте формы
    useEffect(() => {
        setForm((s) => ({ ...s, sso_protocol: switchSsoChecked ? selectedSsoProvider : "" }));
    }, [ switchSsoChecked, selectedSsoProvider ]);

    const mailBlockInvalid = switchEmailChecked && hasAny(invalidKeys, [
        "auth.smtp_host", "auth.smtp_port", "auth.smtp_from"
    ]);

    const ssoMappingInvalid = switchSsoChecked && hasAny(invalidKeys, [
        "auth.sso_compass_mapping_name"
    ]);

    const ssoOidcInvalid = switchSsoChecked && selectedSsoProvider === "oidc" && hasAny(invalidKeys, [
        "auth.oidc_attribution_mapping_mail",
        "auth.oidc_attribution_mapping_phone_number",
        "auth.oidc_client_id",
        "auth.oidc_client_secret",
        "auth.oidc_oidc_provider_metadata_link",
    ]);

    const ssoLdapInvalid = switchSsoChecked && selectedSsoProvider === "ldap" && hasAny(invalidKeys, [
        "auth.ldap_server_host", "auth.ldap_server_port",
        "auth.ldap_user_search_base", "auth.ldap_user_unique_attribute",
        "auth.ldap_user_search_account_dn", "auth.ldap_user_search_account_password",
    ]);

    const smsAgentInvalid = switchSmsAgentChecked && hasAny(invalidKeys, [
        "auth.sms_agent_app_name", "auth.sms_agent_login", "auth.sms_agent_password"
    ]);
    const vonageInvalid = switchVonageChecked && hasAny(invalidKeys, [
        "auth.vonage_app_name", "auth.vonage_api_key", "auth.vonage_api_secret"
    ]);
    const twilioInvalid = switchTwilioChecked && hasAny(invalidKeys, [
        "auth.twilio_app_name", "auth.twilio_account_sid", "auth.twilio_account_auth_token"
    ]);

    const renderHintLdapLinkDesc = () => {
        const text = t("install_page.hints.sso_title_pt2");
        const target = "инструкцией";
        const i = text.indexOf(target);
        if (i === -1) return text;

        return (
            <>
                {text.slice(0, i)}
                <a
                    href="https://doc-onpremise.getcompass.ru/service-guide.html#sso-active-directory"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[#009fe6] hover:text-[#0082bd]"
                >
                    {target}
                </a>
                {text.slice(i + target.length)}
            </>
        );
    };

    const renderHintLdapConnectSubtitleLinkDesc = () => {
        const text = t("install_page.hints.ldap_connect_subtitle");
        const target = "ссылке";
        const i = text.indexOf(target);
        if (i === -1) return text;

        return (
            <>
                {text.slice(0, i)}
                <a
                    href="https://doc-onpremise.getcompass.ru/service-guide.html#sso-active-directory"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[#009fe6] hover:text-[#0082bd]"
                >
                    {target}
                </a>
                {text.slice(i + target.length)}
            </>
        );
    };

    const renderHintListItem = (text: string, target: string) => {

        const i = text.indexOf(target);
        if (i === -1) return text;

        return (
            <div className="flex">
                <div className="px-[7px] py-[6px]">
                    <div
                        className="w-[5px] h-[5px] rounded-full bg-[rgba(255,255,255,0.8)]" />
                </div>
                <Text size="tooltip">
                    {text.slice(0, i)}
                    <span className="font-lato-bold">
                        {target}
                    </span>
                    {text.slice(i + target.length)}
                </Text>
            </div>
        );
    }

    return (
        <div className="flex flex-col items-start justify-start gap-[32px] w-full">
            <DashedLine />
            <div className="flex flex-col items-start justify-start gap-[12px] px-[8px]">
                <div ref={ref} id="section-auth" />
                <Text variant="bold" size="xl" className="tracking-[-0.15px]">
                    {t("install_page.configure.auth_block.title")}
                </Text>
                <Text className="tracking-[-0.15px] whitespace-pre-line">
                    {t("install_page.configure.auth_block.desc")}
                </Text>
            </div>

            <div className="flex flex-row flex-wrap gap-[32px] grow w-full">

                {/* mail */}
                <div className="flex flex-col gap-[19px] grow max-w-[256px] min-w-[256px] shrink-0">
                    <Text variant="bold" className="pl-[8px]">
                        {t("install_page.configure.auth_block.mail_auth_title")}
                        <Tooltip classNameContent="max-w-[546px]" side="right"
                                 trigger={<TooltipIcon className="w-[16px] h-[16px] ml-[4px]" />}>
                            <div className="flex flex-col gap-[6px]">
                                <Text size="tooltip" className="whitespace-pre-line">
                                    {t("install_page.hints.mail_block_title")}
                                </Text>
                                <LinkList linkList={[
                                    {
                                        label: t("install_page.hints.mail_block_title_link_gmail"),
                                        link: "https://doc-onpremise.getcompass.ru/service-guide.html#gmail"
                                    },
                                    {
                                        label: t("install_page.hints.mail_block_title_link_yandex"),
                                        link: "https://doc-onpremise.getcompass.ru/service-guide.html#page-label-service-guide-mail-yandex"
                                    },
                                ]} />
                            </div>
                        </Tooltip>
                    </Text>
                    <div className={cn(
                        "flex flex-col gap-[1px] border-[1px] rounded-[12px]",
                        mailBlockInvalid || invalidKeys.has("auth.auth_methods") ? "border-[#ff4f47]" : "border-transparent"
                    )}>
                        <AuthSwitcherBlock
                            id="switch-auth-mail"
                            text={t("install_page.configure.auth_block.mail_switcher_title")}
                            checked={switchEmailChecked}
                            onCheckedChange={setSwitchEmailChecked}
                            clearInvalidKey={clearInvalidKey}
                            tooltip={
                                <Tooltip classNameContent="max-w-[481px]" side="right"
                                         trigger={<TooltipIcon className="w-[18px] h-[18px] ml-[4px]" />}>
                                    <Text size="tooltip" className="whitespace-pre-line">
                                        {t("install_page.hints.mail_title")}
                                    </Text>
                                </Tooltip>
                            }
                        />
                        {switchEmailChecked && (
                            <>
                                <InputBlock
                                    label={t("install_page.configure.auth_block.mail_host_input_title")}
                                    placeholder={t("install_page.configure.auth_block.mail_host_input_placeholder")}
                                    requiredField
                                    name="smtp_host"
                                    value={form.smtp_host}
                                    onChange={(v) => {
                                        setForm((s) => ({ ...s, smtp_host: v }));
                                        clearInvalidKey("auth.smtp_host");
                                    }}
                                    invalid={invalidKeys.has("auth.smtp_host")}
                                />
                                <InputBlock
                                    label={t("install_page.configure.auth_block.mail_port_input_title")}
                                    placeholder={t("install_page.configure.auth_block.mail_port_input_placeholder")}
                                    requiredField
                                    name="smtp_port"
                                    value={form.smtp_port}
                                    onChange={(v) => {
                                        setForm((s) => ({ ...s, smtp_port: v }));
                                        clearInvalidKey("auth.smtp_port");
                                    }}
                                    type="number"
                                    invalid={invalidKeys.has("auth.smtp_port")}
                                />
                                <InputBlock
                                    label={t("install_page.configure.auth_block.mail_login_input_title")}
                                    placeholder={t("install_page.configure.auth_block.mail_login_input_placeholder")}
                                    name="smtp_user"
                                    value={form.smtp_user}
                                    onChange={(v) => setForm((s) => ({ ...s, smtp_user: v }))}
                                />
                                <InputBlock
                                    label={t("install_page.configure.auth_block.mail_password_input_title")}
                                    placeholder={t("install_page.configure.auth_block.mail_password_input_placeholder")}
                                    name="smtp_pass"
                                    value={form.smtp_pass}
                                    onChange={(v) => setForm((s) => ({ ...s, smtp_pass: v }))}
                                    type="password"
                                />
                                <SelectorBlock
                                    label={t("install_page.configure.auth_block.mail_encryption_title")}
                                    name="smtp_encryption"
                                    value={form.smtp_encryption}
                                    onChange={(v) => setForm((s) => ({
                                        ...s,
                                        smtp_encryption: v as AuthFormState["smtp_encryption"]
                                    }))}
                                    defaultValue="none"
                                    values={[
                                        {
                                            key: "none",
                                            label: t("install_page.configure.auth_block.mail_encryption_none")
                                        },
                                        {
                                            key: "tls",
                                            label: t("install_page.configure.auth_block.mail_encryption_tls")
                                        },
                                        {
                                            key: "ssl",
                                            label: t("install_page.configure.auth_block.mail_encryption_ssl")
                                        },
                                    ]}
                                />
                                <InputBlock
                                    label={t("install_page.configure.auth_block.mail_from_input_title")}
                                    placeholder={t("install_page.configure.auth_block.mail_from_input_placeholder")}
                                    className="rounded-b-[12px]"
                                    requiredField
                                    name="smtp_from"
                                    value={form.smtp_from}
                                    onChange={(v) => {
                                        setForm((s) => ({ ...s, smtp_from: v }));
                                        clearInvalidKey("auth.smtp_from");
                                    }}
                                    type="email"
                                    inputProps={{
                                        onBlur: (e) => {
                                            const val = e.currentTarget.value.trim();

                                            if (val.length < 1) {
                                                return;
                                            }

                                            if (!isValidEmail(val)) {
                                                markInvalidKey("auth.smtp_from");
                                                return;
                                            }
                                            clearInvalidKey("auth.smtp_from");
                                        }
                                    }}
                                    invalid={invalidKeys.has("auth.smtp_from")}
                                />
                            </>
                        )}
                    </div>
                </div>

                {/* sso */}
                <div className="flex flex-col gap-[19px] grow max-w-[256px] min-w-[256px] shrink-0">
                    <Text variant="bold" className="pl-[8px]">
                        {t("install_page.configure.auth_block.sso_auth_title")}
                        <Tooltip classNameContent="max-w-[407px]" side="right"
                                 trigger={<TooltipIcon className="w-[16px] h-[16px] ml-[4px]" />}>
                            <Text size="tooltip" className="whitespace-pre-line">
                                {t("install_page.hints.sso_block_title")}
                            </Text>
                        </Tooltip>
                    </Text>
                    <div className={cn(
                        "flex flex-col gap-[1px] border-[1px] rounded-[12px]",
                        (switchSsoChecked && (ssoMappingInvalid || ssoOidcInvalid || ssoLdapInvalid)
                            || invalidKeys.has("auth.auth_methods")) ? "border-[#ff4f47]" : "border-transparent"
                    )}>
                        <AuthSwitcherBlock
                            id="switch-auth-sso"
                            text={t("install_page.configure.auth_block.sso_switcher_title")}
                            checked={switchSsoChecked}
                            onCheckedChange={setSwitchSsoChecked}
                            clearInvalidKey={clearInvalidKey}
                            tooltip={
                                <Tooltip classNameContent="max-w-[543px]" side="right"
                                         trigger={<TooltipIcon className="w-[18px] h-[18px] ml-[4px]" />}>
                                    <div className="flex flex-col gap-[6px]">
                                        <Text size="tooltip" className="whitespace-pre-line">
                                            {t("install_page.hints.sso_title_pt1")}
                                        </Text>
                                        <LinkList linkList={[
                                            {
                                                label: t("install_page.hints.sso_title_link_adfs"),
                                                link: "https://doc-onpremise.getcompass.ru/service-guide.html#sso-ad-fs"
                                            },
                                            {
                                                label: t("install_page.hints.sso_title_link_okta"),
                                                link: "https://doc-onpremise.getcompass.ru/service-guide.html#sso-okta"
                                            },
                                            {
                                                label: t("install_page.hints.sso_title_link_keycloak"),
                                                link: "https://doc-onpremise.getcompass.ru/service-guide.html#sso-keycloak"
                                            },
                                        ]} />
                                        <Text size="tooltip" className="whitespace-pre-line">
                                            {renderHintLdapLinkDesc()}
                                        </Text>
                                    </div>
                                </Tooltip>
                            }
                        />
                        {switchSsoChecked && (
                            <>
                                <div className="flex gap-[1px]">
                                    <Text
                                        size="sm"
                                        className={`text-center cursor-pointer 
                                        ${selectedSsoProvider === "oidc" ? "bg-[rgba(0,0,0,0.1)]" : "bg-[rgba(0,0,0,0.2)]"} 
                                        ${selectedSsoProvider === "oidc" ? "text-[rgba(255,255,255,0.8)]" : "text-[#54555c]"} 
                                        p-[12px] w-full grow`}
                                        onClick={() => setSelectedSsoProvider("oidc")}>
                                        {t("install_page.configure.auth_block.sso_provider_oidc")}
                                    </Text>
                                    <Text
                                        size="sm"
                                        className={`text-center cursor-pointer 
                                        ${selectedSsoProvider === "ldap" ? "bg-[rgba(0,0,0,0.1)]" : "bg-[rgba(0,0,0,0.2)]"} 
                                        ${selectedSsoProvider === "ldap" ? "text-[rgba(255,255,255,0.8)]" : "text-[#54555c]"} 
                                        p-[12px] w-full grow`}
                                        onClick={() => setSelectedSsoProvider("ldap")}>
                                        {t("install_page.configure.auth_block.sso_provider_ldap")}
                                    </Text>
                                </div>
                                <SubTitleBlock label={t("install_page.configure.auth_block.sso_mapping_subtitle")}
                                               tooltip={
                                                   <Tooltip
                                                       classNameContent="max-w-[566px]" side="right"
                                                       trigger={
                                                           <TooltipIcon className="w-[16px] h-[16px] ml-[4px]" />
                                                       }
                                                   >
                                                       <div className="flex flex-col gap-[12px]">
                                                           <Text size="tooltip" className="whitespace-pre-line">
                                                               {(() => {
                                                                   const text = t("install_page.hints.sso_mapping_attributes_subtitle_pt1");
                                                                   const target_name = "Имя, Электронная почта";
                                                                   const target_phone_number = "Номер пользователя";
                                                                   const i_name = text.indexOf(target_name);
                                                                   const i_phone_number = text.indexOf(target_phone_number);
                                                                   if (i_name === -1 || i_phone_number === -1) return text;

                                                                   return (
                                                                       <>
                                                                           {text.slice(0, i_name)}
                                                                           <span className="font-lato-bold">
                                                                           {target_name}
                                                                           </span>
                                                                           {text.slice(i_name + target_name.length, i_phone_number)}
                                                                           <span className="font-lato-bold">
                                                                           {target_phone_number}
                                                                           </span>
                                                                           {text.slice(i_phone_number + target_phone_number.length)}
                                                                       </>
                                                                   );
                                                               })()}
                                                           </Text>
                                                           <Text size="tooltip" className="whitespace-pre-line">
                                                               {(() => {
                                                                   const text = t("install_page.hints.sso_mapping_attributes_subtitle_pt2");
                                                                   const target = "{first_name}";
                                                                   const i = text.indexOf(target);
                                                                   if (i === -1) return text;

                                                                   return (
                                                                       <>
                                                                           {text.slice(0, i)}
                                                                           <span className="font-lato-bold">
                                                                           {target}
                                                                           </span>
                                                                           {text.slice(i + target.length)}
                                                                       </>
                                                                   );
                                                               })()}
                                                           </Text>
                                                           <Text size="tooltip" className="whitespace-pre-line">
                                                               {(() => {
                                                                   const text = t("install_page.hints.sso_mapping_attributes_subtitle_pt3");
                                                                   const target_example_1 = "{first_name} {last_name}";
                                                                   const target_example_2 = "{first_name}-{last_name}";
                                                                   const i_example_1 = text.indexOf(target_example_1);
                                                                   const i_example_2 = text.indexOf(target_example_2);
                                                                   if (i_example_1 === -1 || i_example_2 === -1) return text;

                                                                   return (
                                                                       <>
                                                                           {text.slice(0, i_example_1)}
                                                                           <span className="font-lato-bold">
                                                                           {target_example_1}
                                                                           </span>
                                                                           {text.slice(i_example_1 + target_example_1.length, i_example_2)}
                                                                           <span className="font-lato-bold">
                                                                           {target_example_2}
                                                                           </span>
                                                                           {text.slice(i_example_2 + target_example_2.length)}
                                                                       </>
                                                                   );
                                                               })()}
                                                           </Text>
                                                       </div>
                                                   </Tooltip>
                                               } />
                                <InputBlock
                                    label={t("install_page.configure.auth_block.sso_mapping_name_input_title")}
                                    placeholder={t("install_page.configure.auth_block.sso_mapping_name_input_placeholder")}
                                    requiredField
                                    name="sso_compass_mapping_name"
                                    value={form.sso_compass_mapping_name}
                                    onChange={(v) => {
                                        setForm((s) => ({ ...s, sso_compass_mapping_name: v }));
                                        clearInvalidKey("auth.sso_compass_mapping_name");
                                    }}
                                    invalid={invalidKeys.has("auth.sso_compass_mapping_name")}
                                />
                                <InputBlock
                                    label={t("install_page.configure.auth_block.sso_mapping_avatar_input_title")}
                                    placeholder={t("install_page.configure.auth_block.sso_mapping_avatar_input_placeholder")}
                                    name="sso_compass_mapping_avatar"
                                    value={form.sso_compass_mapping_avatar}
                                    onChange={(v) => setForm((s) => ({ ...s, sso_compass_mapping_avatar: v }))}
                                />
                                <InputBlock
                                    label={t("install_page.configure.auth_block.sso_mapping_badge_input_title")}
                                    placeholder={t("install_page.configure.auth_block.sso_mapping_badge_input_placeholder")}
                                    name="sso_compass_mapping_badge"
                                    value={form.sso_compass_mapping_badge}
                                    onChange={(v) => setForm((s) => ({ ...s, sso_compass_mapping_badge: v }))}
                                />
                                <InputBlock
                                    label={t("install_page.configure.auth_block.sso_mapping_role_input_title")}
                                    placeholder={t("install_page.configure.auth_block.sso_mapping_role_input_placeholder")}
                                    name="sso_compass_mapping_role"
                                    value={form.sso_compass_mapping_role}
                                    onChange={(v) => setForm((s) => ({ ...s, sso_compass_mapping_role: v }))}
                                />
                                <InputBlock
                                    label={t("install_page.configure.auth_block.sso_mapping_bio_input_title")}
                                    placeholder={t("install_page.configure.auth_block.sso_mapping_bio_input_placeholder")}
                                    name="sso_compass_mapping_bio"
                                    value={form.sso_compass_mapping_bio}
                                    onChange={(v) => setForm((s) => ({ ...s, sso_compass_mapping_bio: v }))}
                                />
                                {selectedSsoProvider === "oidc" && (
                                    <>
                                        <InputBlock
                                            label={t("install_page.configure.auth_block.sso_mapping_mail_input_title")}
                                            placeholder={t("install_page.configure.auth_block.sso_mapping_mail_input_placeholder")}
                                            requiredField
                                            name="oidc_attribution_mapping_mail"
                                            value={form.oidc_attribution_mapping_mail}
                                            onChange={(v) => {
                                                setForm((s) => ({ ...s, oidc_attribution_mapping_mail: v }));
                                                clearInvalidKey("auth.oidc_attribution_mapping_mail");
                                            }}
                                            invalid={invalidKeys.has("auth.oidc_attribution_mapping_mail")}
                                        />
                                        <InputBlock
                                            label={t("install_page.configure.auth_block.sso_mapping_phone_number_input_title")}
                                            placeholder={t("install_page.configure.auth_block.sso_mapping_phone_number_input_placeholder")}
                                            requiredField
                                            name="oidc_attribution_mapping_phone_number"
                                            value={form.oidc_attribution_mapping_phone_number}
                                            onChange={(v) => {
                                                setForm((s) => ({ ...s, oidc_attribution_mapping_phone_number: v }));
                                                clearInvalidKey("auth.oidc_attribution_mapping_phone_number");
                                            }}
                                            invalid={invalidKeys.has("auth.oidc_attribution_mapping_phone_number")}
                                        />
                                    </>
                                )}
                                <SubTitleBlock
                                    label={t("install_page.configure.auth_block.sso_connection_subtitle")}
                                    tooltip={
                                        selectedSsoProvider === "oidc" ? (
                                            <Tooltip classNameContent="max-w-[477px]" side="right"
                                                     trigger={<TooltipIcon className="w-[16px] h-[16px] ml-[4px]" />}>
                                                <div className="flex flex-col gap-[6px]">
                                                    <Text size="tooltip" className="whitespace-pre-line">
                                                        {t("install_page.hints.sso_connect_subtitle")}
                                                    </Text>
                                                    <LinkList linkList={[
                                                        {
                                                            label: t("install_page.hints.sso_connect_subtitle_adfs"),
                                                            link: "https://doc-onpremise.getcompass.ru/service-guide.html#sso-ad-fs"
                                                        },
                                                        {
                                                            label: t("install_page.hints.sso_connect_subtitle_okta"),
                                                            link: "https://doc-onpremise.getcompass.ru/service-guide.html#sso-okta"
                                                        },
                                                        {
                                                            label: t("install_page.hints.sso_connect_subtitle_keycloak"),
                                                            link: "https://doc-onpremise.getcompass.ru/service-guide.html#sso-keycloak"
                                                        },
                                                    ]} />
                                                </div>
                                            </Tooltip>
                                        ) : (
                                            <Tooltip classNameContent="max-w-[366px]" side="right"
                                                     trigger={
                                                         <TooltipIcon className="w-[16px] h-[16px] ml-[4px]" />
                                                     }>
                                                <Text size="tooltip" className="whitespace-pre-line">
                                                    {renderHintLdapConnectSubtitleLinkDesc()}
                                                </Text>
                                            </Tooltip>
                                        )
                                    } />
                                {selectedSsoProvider === "oidc" ? (
                                    <>
                                        <InputBlock
                                            label={t("install_page.configure.auth_block.sso_oidc_client_id_input_title")}
                                            placeholder={t("install_page.configure.auth_block.sso_oidc_client_id_input_placeholder")}
                                            requiredField
                                            name="oidc_client_id"
                                            value={form.oidc_client_id}
                                            onChange={(v) => {
                                                setForm((s) => ({ ...s, oidc_client_id: v }));
                                                clearInvalidKey("auth.oidc_client_id");
                                            }}
                                            invalid={invalidKeys.has("auth.oidc_client_id")}
                                        />
                                        <InputBlock
                                            label={t("install_page.configure.auth_block.sso_oidc_client_secret_input_title")}
                                            placeholder={t("install_page.configure.auth_block.sso_oidc_client_secret_input_placeholder")}
                                            requiredField
                                            name="oidc_client_secret"
                                            value={form.oidc_client_secret}
                                            onChange={(v) => {
                                                setForm((s) => ({ ...s, oidc_client_secret: v }));
                                                clearInvalidKey("auth.oidc_client_secret");
                                            }}
                                            type="password"
                                            invalid={invalidKeys.has("auth.oidc_client_secret")}
                                        />
                                        <InputBlock
                                            label={t("install_page.configure.auth_block.sso_oidc_metadata_link_input_title")}
                                            placeholder={t("install_page.configure.auth_block.sso_oidc_metadata_link_input_placeholder")}
                                            requiredField
                                            name="oidc_oidc_provider_metadata_link"
                                            value={form.oidc_oidc_provider_metadata_link}
                                            onChange={(v) => {
                                                setForm((s) => ({ ...s, oidc_oidc_provider_metadata_link: v }));
                                                clearInvalidKey("auth.oidc_oidc_provider_metadata_link");
                                            }}
                                            inputProps={{ type: "url", pattern: "https?://.*" }}
                                            invalid={invalidKeys.has("auth.oidc_oidc_provider_metadata_link")}
                                            className="rounded-b-[12px]"
                                        />
                                    </>
                                ) : (
                                    <>
                                        <InputBlock
                                            label={t("install_page.configure.auth_block.sso_ldap_host_input_title")}
                                            placeholder={t("install_page.configure.auth_block.sso_ldap_host_input_placeholder")}
                                            requiredField
                                            name="ldap_server_host"
                                            value={form.ldap_server_host}
                                            onChange={(v) => {
                                                setForm((s) => ({ ...s, ldap_server_host: v }));
                                                clearInvalidKey("auth.ldap_server_host");
                                            }}
                                            invalid={invalidKeys.has("auth.ldap_server_host")}
                                        />
                                        <InputBlock
                                            label={t("install_page.configure.auth_block.sso_ldap_port_input_title")}
                                            placeholder={t("install_page.configure.auth_block.sso_ldap_port_input_placeholder")}
                                            requiredField
                                            name="ldap_server_port"
                                            value={form.ldap_server_port}
                                            onChange={(v) => {
                                                setForm((s) => ({ ...s, ldap_server_port: v }));
                                                clearInvalidKey("auth.ldap_server_port");
                                            }}
                                            type="number"
                                            invalid={invalidKeys.has("auth.ldap_server_port")}
                                        />
                                        <div
                                            className="flex gap-[8px] items-center justify-start bg-[rgba(0,0,0,0.1)] px-[16px] py-[12px]">
                                            <input type="hidden" name="ldap_use_ssl"
                                                   value={checkboxLdapUseSslChecked ? "true" : "false"} readOnly />
                                            <Checkbox
                                                id="sso-ldap-use-ssl"
                                                checked={checkboxLdapUseSslChecked}
                                                onCheckedChange={setCheckboxLdapUseSslChecked}
                                            />
                                            <Label htmlFor="sso-ldap-use-ssl"
                                                   className="cursor-pointer text-[12px] leading-[18px]">
                                                {t("install_page.configure.auth_block.sso_ldap_use_ssl_checkbox")}
                                            </Label>
                                        </div>
                                        <SelectorBlock
                                            label={t("install_page.configure.auth_block.sso_ldap_cert_strategy_title")}
                                            tooltip={
                                                <Tooltip
                                                    classNameContent="max-w-[473px]"
                                                    side="right"
                                                    trigger={
                                                        <TooltipIcon className="w-[16px] h-[16px] ml-[4px]" />
                                                    }
                                                >
                                                    <div className="flex flex-col gap-[6px]">
                                                        <Text size="tooltip" className="whitespace-pre-line">
                                                            {t("install_page.hints.ldap_require_cert_strategy_subtitle")}
                                                        </Text>
                                                        <div className="flex flex-col">
                                                            {renderHintListItem(t("install_page.hints.ldap_require_cert_strategy_subtitle_never"), "never")}
                                                            {renderHintListItem(t("install_page.hints.ldap_require_cert_strategy_subtitle_allow"), "allow")}
                                                            {renderHintListItem(t("install_page.hints.ldap_require_cert_strategy_subtitle_try"), "try")}
                                                            {renderHintListItem(t("install_page.hints.ldap_require_cert_strategy_subtitle_demand"), "demand")}
                                                        </div>
                                                    </div>
                                                </Tooltip>
                                            }
                                            name="ldap_require_cert_strategy"
                                            value={form.ldap_require_cert_strategy}
                                            onChange={(v) => setForm((s) => ({
                                                ...s,
                                                ldap_require_cert_strategy: v as AuthFormState["ldap_require_cert_strategy"]
                                            }))}
                                            defaultValue="demand"
                                            values={[
                                                {
                                                    key: "never",
                                                    label: t("install_page.configure.auth_block.sso_ldap_cert_strategy_never")
                                                },
                                                {
                                                    key: "allow",
                                                    label: t("install_page.configure.auth_block.sso_ldap_cert_strategy_allow")
                                                },
                                                {
                                                    key: "try",
                                                    label: t("install_page.configure.auth_block.sso_ldap_cert_strategy_try")
                                                },
                                                {
                                                    key: "demand",
                                                    label: t("install_page.configure.auth_block.sso_ldap_cert_strategy_demand")
                                                },
                                            ]}
                                        />
                                        <InputBlock
                                            label={t("install_page.configure.auth_block.sso_ldap_user_search_base_input_title")}
                                            placeholder={t("install_page.configure.auth_block.sso_ldap_user_search_base_input_placeholder")}
                                            requiredField
                                            name="ldap_user_search_base"
                                            value={form.ldap_user_search_base}
                                            onChange={(v) => {
                                                setForm((s) => ({ ...s, ldap_user_search_base: v }));
                                                clearInvalidKey("auth.ldap_user_search_base");
                                            }}
                                            invalid={invalidKeys.has("auth.ldap_user_search_base")}
                                        />
                                        <InputBlock
                                            label={t("install_page.configure.auth_block.sso_ldap_user_unique_attribute_input_title")}
                                            placeholder={t("install_page.configure.auth_block.sso_ldap_user_unique_attribute_input_placeholder")}
                                            requiredField
                                            name="ldap_user_unique_attribute"
                                            value={form.ldap_user_unique_attribute}
                                            onChange={(v) => {
                                                setForm((s) => ({ ...s, ldap_user_unique_attribute: v }));
                                                clearInvalidKey("auth.ldap_user_unique_attribute");
                                            }}
                                            invalid={invalidKeys.has("auth.ldap_user_unique_attribute")}
                                        />
                                        <InputBlock
                                            label={t("install_page.configure.auth_block.sso_ldap_user_search_filter_input_title")}
                                            placeholder={t("install_page.configure.auth_block.sso_ldap_user_search_filter_input_placeholder")}
                                            name="ldap_user_search_filter"
                                            value={form.ldap_user_search_filter}
                                            onChange={(v) => setForm((s) => ({ ...s, ldap_user_search_filter: v }))}
                                        />
                                        <SubTitleBlock
                                            label={t("install_page.configure.auth_block.sso_ldap_service_user_subtitle")}
                                            tooltip={
                                                <Tooltip
                                                    classNameContent="max-w-[306px]"
                                                    side="right"
                                                    trigger={
                                                        <TooltipIcon className="w-[16px] h-[16px] ml-[4px]" />
                                                    }
                                                >
                                                    <Text size="tooltip" className="whitespace-pre-line">
                                                        {t("install_page.hints.ldap_search_account_subtitle")}
                                                    </Text>
                                                </Tooltip>
                                            } />
                                        <InputBlock
                                            label={t("install_page.configure.auth_block.sso_ldap_user_search_account_dn_input_title")}
                                            placeholder={t("install_page.configure.auth_block.sso_ldap_user_search_account_dn_input_placeholder")}
                                            requiredField
                                            name="ldap_user_search_account_dn"
                                            value={form.ldap_user_search_account_dn}
                                            onChange={(v) => {
                                                setForm((s) => ({ ...s, ldap_user_search_account_dn: v }));
                                                clearInvalidKey("auth.ldap_user_search_account_dn");
                                            }}
                                            invalid={invalidKeys.has("auth.ldap_user_search_account_dn")}
                                            tooltip={
                                                <Tooltip
                                                    classNameContent="max-w-[348px]"
                                                    side="right"
                                                    trigger={
                                                        <TooltipIcon className="w-[16px] h-[16px]" />
                                                    }
                                                >
                                                    <Text size="tooltip" className="whitespace-pre-line">
                                                        {t("install_page.hints.ldap_search_account_dn_input")}
                                                    </Text>
                                                </Tooltip>
                                            }
                                        />
                                        <InputBlock
                                            label={t("install_page.configure.auth_block.sso_ldap_user_search_account_password_input_title")}
                                            placeholder={t("install_page.configure.auth_block.sso_ldap_user_search_account_password_input_placeholder")}
                                            requiredField
                                            name="ldap_user_search_account_password"
                                            value={form.ldap_user_search_account_password}
                                            onChange={(v) => {
                                                setForm((s) => ({ ...s, ldap_user_search_account_password: v }));
                                                clearInvalidKey("auth.ldap_user_search_account_password");
                                            }}
                                            type="password"
                                            invalid={invalidKeys.has("auth.ldap_user_search_account_password")}
                                        />
                                        <div className="
                                        flex gap-[8px] items-center justify-start
                                        bg-[rgba(0,0,0,0.1)] px-[16px] py-[12px] rounded-b-[12px]
                                        ">
                                            <input
                                                type="hidden"
                                                name="ldap_account_disabling_monitoring_enabled"
                                                value={checkboxAccountDisablingMonitoringEnabledChecked ? "true" : "false"}
                                                readOnly
                                            />
                                            <Checkbox
                                                id="sso-ldap-account-disabling-monitoring-enabled"
                                                checked={checkboxAccountDisablingMonitoringEnabledChecked}
                                                onCheckedChange={(checked) => setCheckboxAccountDisablingMonitoringEnabledChecked(checked)} />
                                            <Label
                                                htmlFor="sso-ldap-account-disabling-monitoring-enabled"
                                                className="cursor-pointer text-[12px] leading-[18px]"
                                            >
                                                {t("install_page.configure.auth_block.sso_ldap_account_disabling_monitoring_enabled_checkbox")}
                                                <Tooltip
                                                    classNameContent="max-w-[450px]"
                                                    side="right"
                                                    trigger={
                                                        <TooltipIcon className="w-[16px] h-[16px] ml-[4px]" />
                                                    }
                                                >
                                                    <Text size="tooltip" className="whitespace-pre-line">
                                                        {t("install_page.hints.ldap_monitoring_checkbox")}
                                                    </Text>
                                                </Tooltip>
                                            </Label>
                                        </div>
                                    </>
                                )}
                            </>
                        )}
                    </div>
                </div>

                {/* sms */}
                <div className="flex flex-col gap-[19px] grow max-w-[256px] min-w-[256px] shrink-0">
                    <Text variant="bold" className="pl-[8px]">
                        {t("install_page.configure.auth_block.sms_auth_title")}
                        <Tooltip classNameContent="max-w-[378px]" side="right"
                                 trigger={<TooltipIcon className="w-[16px] h-[16px] ml-[4px]" />}>
                            <Text size="tooltip" className="whitespace-pre-line">
                                {t("install_page.hints.sms_block_title")}
                            </Text>
                        </Tooltip>
                    </Text>
                    <div className="flex flex-col gap-[6px]">

                        {/* sms_agent */}
                        <div className={cn(
                            "flex flex-col gap-[1px] border-[1px] rounded-[12px]",
                            smsAgentInvalid || invalidKeys.has("auth.auth_methods") ? "border-[#ff4f47]" : "border-transparent"
                        )}>
                            <AuthSwitcherBlock
                                id="switch-auth-sms-agent"
                                text={t("install_page.configure.auth_block.sms_sms_agent_switcher_title")}
                                checked={switchSmsAgentChecked}
                                onCheckedChange={setSwitchSmsAgentChecked}
                                clearInvalidKey={clearInvalidKey}
                                tooltip={
                                    <Tooltip
                                        classNameContent="max-w-[320px]"
                                        side="right"
                                        trigger={
                                            <TooltipIcon className="w-[18px] h-[18px] ml-[4px]" />
                                        }
                                    >
                                        <Text size="tooltip" className="whitespace-pre-line">
                                            {(() => {
                                                const text = t("install_page.hints.sms_agent_title");
                                                const target = "ссылке";
                                                const i = text.indexOf(target);
                                                if (i === -1) return text;

                                                return (
                                                    <>
                                                        {text.slice(0, i)}
                                                        <a
                                                            href="https://doc-onpremise.getcompass.ru/service-guide.html#id2"
                                                            target="_blank"
                                                            rel="noopener noreferrer"
                                                            className="text-[#009fe6] hover:text-[#0082bd]"
                                                        >
                                                            {target}
                                                        </a>
                                                        {text.slice(i + target.length)}
                                                    </>
                                                );
                                            })()}
                                        </Text>
                                    </Tooltip>
                                }
                            />
                            {switchSmsAgentChecked && (
                                <>
                                    <InputBlock
                                        label={t("install_page.configure.auth_block.sms_sms_agent_from_input_title")}
                                        placeholder={t("install_page.configure.auth_block.sms_sms_agent_from_input_placeholder")}
                                        requiredField
                                        name="sms_agent_app_name"
                                        value={form.sms_agent_app_name}
                                        onChange={(v) => {
                                            setForm((s) => ({ ...s, sms_agent_app_name: v }));
                                            clearInvalidKey("auth.sms_agent_app_name");
                                        }}
                                        invalid={invalidKeys.has("auth.sms_agent_app_name")}
                                    />
                                    <InputBlock
                                        label={t("install_page.configure.auth_block.sms_sms_agent_login_input_title")}
                                        placeholder={t("install_page.configure.auth_block.sms_sms_agent_login_input_placeholder")}
                                        requiredField
                                        name="sms_agent_login"
                                        value={form.sms_agent_login}
                                        onChange={(v) => {
                                            setForm((s) => ({ ...s, sms_agent_login: v }));
                                            clearInvalidKey("auth.sms_agent_login");
                                        }}
                                        invalid={invalidKeys.has("auth.sms_agent_login")}
                                    />
                                    <InputBlock
                                        label={t("install_page.configure.auth_block.sms_sms_agent_password_input_title")}
                                        placeholder={t("install_page.configure.auth_block.sms_sms_agent_password_input_placeholder")}
                                        className="rounded-b-[12px]"
                                        requiredField
                                        name="sms_agent_password"
                                        value={form.sms_agent_password}
                                        onChange={(v) => {
                                            setForm((s) => ({ ...s, sms_agent_password: v }));
                                            clearInvalidKey("auth.sms_agent_password");
                                        }}
                                        type="password"
                                        invalid={invalidKeys.has("auth.sms_agent_password")}
                                    />
                                </>
                            )}
                        </div>

                        {/* vonage */}
                        <div className={cn(
                            "flex flex-col gap-[1px] border-[1px] rounded-[12px]",
                            vonageInvalid || invalidKeys.has("auth.auth_methods") ? "border-[#ff4f47]" : "border-transparent"
                        )}>
                            <AuthSwitcherBlock
                                id="switch-auth-vonage"
                                text={t("install_page.configure.auth_block.sms_vonage_switcher_title")}
                                checked={switchVonageChecked}
                                onCheckedChange={setSwitchVonageChecked}
                                clearInvalidKey={clearInvalidKey}
                                tooltip={
                                    <Tooltip
                                        classNameContent="max-w-[320px]"
                                        side="right"
                                        trigger={
                                            <TooltipIcon className="w-[18px] h-[18px] ml-[4px]" />
                                        }
                                    >
                                        <Text size="tooltip" className="whitespace-pre-line">
                                            {(() => {
                                                const text = t("install_page.hints.vonage_title");
                                                const target = "ссылке";
                                                const i = text.indexOf(target);
                                                if (i === -1) return text;

                                                return (
                                                    <>
                                                        {text.slice(0, i)}
                                                        <a
                                                            href="https://doc-onpremise.getcompass.ru/service-guide.html#vonage"
                                                            target="_blank"
                                                            rel="noopener noreferrer"
                                                            className="text-[#009fe6] hover:text-[#0082bd]"
                                                        >
                                                            {target}
                                                        </a>
                                                        {text.slice(i + target.length)}
                                                    </>
                                                );
                                            })()}
                                        </Text>
                                    </Tooltip>
                                }
                            />
                            {switchVonageChecked && (
                                <>
                                    <InputBlock
                                        label={t("install_page.configure.auth_block.sms_vonage_from_input_title")}
                                        placeholder={t("install_page.configure.auth_block.sms_vonage_from_input_placeholder")}
                                        requiredField
                                        name="vonage_app_name"
                                        value={form.vonage_app_name}
                                        onChange={(v) => {
                                            setForm((s) => ({ ...s, vonage_app_name: v }));
                                            clearInvalidKey("auth.vonage_app_name");
                                        }}
                                        invalid={invalidKeys.has("auth.vonage_app_name")}
                                    />
                                    <InputBlock
                                        label={t("install_page.configure.auth_block.sms_vonage_api_key_input_title")}
                                        placeholder={t("install_page.configure.auth_block.sms_vonage_api_key_input_placeholder")}
                                        requiredField
                                        name="vonage_api_key"
                                        value={form.vonage_api_key}
                                        onChange={(v) => {
                                            setForm((s) => ({ ...s, vonage_api_key: v }));
                                            clearInvalidKey("auth.vonage_api_key");
                                        }}
                                        invalid={invalidKeys.has("auth.vonage_api_key")}
                                    />
                                    <InputBlock
                                        label={t("install_page.configure.auth_block.sms_vonage_api_secret_input_title")}
                                        placeholder={t("install_page.configure.auth_block.sms_vonage_api_secret_input_placeholder")}
                                        className="rounded-b-[12px]"
                                        requiredField
                                        name="vonage_api_secret"
                                        value={form.vonage_api_secret}
                                        onChange={(v) => {
                                            setForm((s) => ({ ...s, vonage_api_secret: v }));
                                            clearInvalidKey("auth.vonage_api_secret");
                                        }}
                                        type="password"
                                        invalid={invalidKeys.has("auth.vonage_api_secret")}
                                    />
                                </>
                            )}
                        </div>

                        {/* twilio */}
                        <div className={cn(
                            "flex flex-col gap-[1px] border-[1px] rounded-[12px]",
                            twilioInvalid || invalidKeys.has("auth.auth_methods") ? "border-[#ff4f47]" : "border-transparent"
                        )}>
                            <AuthSwitcherBlock
                                id="switch-auth-twilio"
                                text={t("install_page.configure.auth_block.sms_twilio_switcher_title")}
                                checked={switchTwilioChecked}
                                onCheckedChange={setSwitchTwilioChecked}
                                clearInvalidKey={clearInvalidKey}
                                tooltip={
                                    <Tooltip
                                        classNameContent="max-w-[320px]"
                                        side="right"
                                        trigger={
                                            <TooltipIcon className="w-[18px] h-[18px] ml-[4px]" />
                                        }
                                    >
                                        <Text size="tooltip" className="whitespace-pre-line">
                                            {(() => {
                                                const text = t("install_page.hints.twilio_title");
                                                const target = "ссылке";
                                                const i = text.indexOf(target);
                                                if (i === -1) return text;

                                                return (
                                                    <>
                                                        {text.slice(0, i)}
                                                        <a
                                                            href="https://doc-onpremise.getcompass.ru/service-guide.html#twilio"
                                                            target="_blank"
                                                            rel="noopener noreferrer"
                                                            className="text-[#009fe6] hover:text-[#0082bd]"
                                                        >
                                                            {target}
                                                        </a>
                                                        {text.slice(i + target.length)}
                                                    </>
                                                );
                                            })()}
                                        </Text>
                                    </Tooltip>
                                }
                            />
                            {switchTwilioChecked && (
                                <>
                                    <InputBlock
                                        label={t("install_page.configure.auth_block.sms_twilio_from_input_title")}
                                        placeholder={t("install_page.configure.auth_block.sms_twilio_from_input_placeholder")}
                                        requiredField
                                        name="twilio_app_name"
                                        value={form.twilio_app_name}
                                        onChange={(v) => {
                                            setForm((s) => ({ ...s, twilio_app_name: v }));
                                            clearInvalidKey("auth.twilio_app_name");
                                        }}
                                        invalid={invalidKeys.has("auth.twilio_app_name")}
                                    />
                                    <InputBlock
                                        label={t("install_page.configure.auth_block.sms_twilio_account_sid_input_title")}
                                        placeholder={t("install_page.configure.auth_block.sms_twilio_account_sid_input_placeholder")}
                                        requiredField
                                        name="twilio_account_sid"
                                        value={form.twilio_account_sid}
                                        onChange={(v) => {
                                            setForm((s) => ({ ...s, twilio_account_sid: v }));
                                            clearInvalidKey("auth.twilio_account_sid");
                                        }}
                                        invalid={invalidKeys.has("auth.twilio_account_sid")}
                                    />
                                    <InputBlock
                                        label={t("install_page.configure.auth_block.sms_twilio_auth_token_input_title")}
                                        placeholder={t("install_page.configure.auth_block.sms_twilio_auth_token_input_placeholder")}
                                        className="rounded-b-[12px]"
                                        requiredField
                                        name="twilio_account_auth_token"
                                        value={form.twilio_account_auth_token}
                                        onChange={(v) => {
                                            setForm((s) => ({ ...s, twilio_account_auth_token: v }));
                                            clearInvalidKey("auth.twilio_account_auth_token");
                                        }}
                                        type="password"
                                        invalid={invalidKeys.has("auth.twilio_account_auth_token")}
                                    />
                                </>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
})
AuthBlock.displayName = "AuthBlock";

/* =========================
   Блок админа
   ========================= */

type AdminBlockProps = AuthSettings & {
    form: AdminFormState;
    setForm: Dispatch<SetStateAction<AdminFormState>>;
    invalidKeys: InvalidKeys;
    markInvalidKey: (k: string) => void;
    clearInvalidKey: (k: string) => void;
};
const AdminBlock = forwardRef<HTMLDivElement, AdminBlockProps>((props, ref) => {
    const t = useLangString();
    const {
        switchEmailChecked, switchSsoChecked, switchSmsAgentChecked, switchVonageChecked, switchTwilioChecked,
        form, setForm, invalidKeys, markInvalidKey, clearInvalidKey,
    } = props;
    const [ mailPasswordErrorVisible, setMailPasswordErrorVisible ] = useState(false);

    const anySmsChecked = switchSmsAgentChecked || switchVonageChecked || switchTwilioChecked;

    const adminMainInvalid = hasAny(invalidKeys, [ "admin.root_user_full_name", "admin.space_name" ]);
    const adminCredsInvalid = hasAny(invalidKeys, [
        ...(switchSsoChecked ? [ "admin.root_user_sso_login" ] : []),
        ...(anySmsChecked ? [ "admin.root_user_phone" ] : []),
        ...(switchEmailChecked ? [ "admin.root_user_mail", "admin.root_user_pass" ] : []),
    ]);

    return (
        <div className="flex flex-col items-start justify-start gap-[32px] w-full">
            <DashedLine />
            <div className="flex flex-col items-start justify-start gap-[12px] px-[8px]">
                <div ref={ref} id="section-admin" />
                <Text variant="bold" size="xl" className="tracking-[-0.15px]">
                    {t("install_page.configure.admin_block.title")}
                </Text>
                <Text className="tracking-[-0.15px]">{t("install_page.configure.admin_block.desc")}</Text>
            </div>

            <div className="flex flex-row flex-wrap gap-[32px] grow w-full">
                <div className="flex flex-col gap-[19px] grow shrink-0">
                    <Text variant="bold" className="pl-[8px]">
                        {t("install_page.configure.admin_block.admin_title")}
                        <Tooltip classNameContent="max-w-[431px]" side="right"
                                 trigger={<TooltipIcon className="w-[16px] h-[16px] ml-[4px]" />}>
                            <Text size="tooltip" className="whitespace-pre-line">
                                {t("install_page.hints.admin_profile_creds_title")}
                            </Text>
                        </Tooltip>
                    </Text>
                    <div className={cn(
                        "flex flex-col gap-[1px] border-[1px] rounded-[12px]",
                        adminMainInvalid ? "border-[#ff4f47]" : "border-transparent"
                    )}>
                        <InputBlock
                            label={t("install_page.configure.admin_block.admin_name_input_title")}
                            placeholder={t("install_page.configure.admin_block.admin_name_input_placeholder")}
                            className="rounded-t-[12px]"
                            requiredField
                            name="root_user_full_name"
                            value={form.root_user_full_name}
                            onChange={(v) => {
                                setForm((s) => ({ ...s, root_user_full_name: v }));
                                clearInvalidKey("admin.root_user_full_name");
                            }}
                            invalid={invalidKeys.has("admin.root_user_full_name")}
                            maxLength={40}
                        />
                        <InputBlock
                            label={t("install_page.configure.admin_block.space_name_input_title")}
                            placeholder={t("install_page.configure.admin_block.space_name_input_placeholder")}
                            className="rounded-b-[12px]"
                            requiredField
                            name="space_name"
                            value={form.space_name}
                            onChange={(v) => {
                                setForm((s) => ({ ...s, space_name: v }));
                                clearInvalidKey("admin.space_name");
                            }}
                            invalid={invalidKeys.has("admin.space_name")}
                            maxLength={40}
                        />
                    </div>
                </div>

                <div className="flex flex-col gap-[19px] grow shrink-0">
                    <Text variant="bold" className="pl-[8px]">
                        {t("install_page.configure.admin_block.admin_creds_title")}
                        <Tooltip classNameContent="max-w-[370px]" side="right"
                                 trigger={<TooltipIcon className="w-[16px] h-[16px] ml-[4px]" />}>
                            <Text size="tooltip" className="whitespace-pre-line">
                                {t("install_page.hints.admin_auth_creds_title")}
                            </Text>
                        </Tooltip>
                    </Text>
                    {!switchSsoChecked && !anySmsChecked && !switchEmailChecked ? (
                        <div className="flex items-center justify-center
                        bg-[rgba(0,0,0,0.1)] rounded-[12px] pt-[43px] pb-[42px] px-[54px]">
                            <Text color="inactive" className="text-center">
                                {t("install_page.configure.admin_block.admin_creds_need_select_auth_method")}
                            </Text>
                        </div>
                    ) : (
                        <div className={cn(
                            "flex flex-col gap-[1px] border-[1px] rounded-[12px]",
                            adminCredsInvalid ? "border-[#ff4f47]" : "border-transparent"
                        )}>
                            {switchSsoChecked && (
                                <InputBlock
                                    label={t("install_page.configure.admin_block.admin_sso_login_input_title")}
                                    placeholder={t("install_page.configure.admin_block.admin_sso_login_input_placeholder")}
                                    className={`rounded-t-[12px] ${!anySmsChecked && !switchEmailChecked ? "rounded-b-[12px]" : ""}`}
                                    requiredField
                                    name="root_user_sso_login"
                                    value={form.root_user_sso_login}
                                    onChange={(v) => {
                                        setForm((s) => ({ ...s, root_user_sso_login: v }));
                                        clearInvalidKey("admin.root_user_sso_login");
                                    }}
                                    invalid={invalidKeys.has("admin.root_user_sso_login")}
                                />
                            )}
                            {anySmsChecked && (
                                <InputBlock
                                    label={t("install_page.configure.admin_block.admin_phone_number_input_title")}
                                    placeholder={t("install_page.configure.admin_block.admin_phone_number_input_placeholder")}
                                    className={`${!switchSsoChecked ? "rounded-t-[12px]" : ""} ${!switchEmailChecked ? "rounded-b-[12px]" : ""}`}
                                    requiredField
                                    name="root_user_phone"
                                    value={form.root_user_phone}
                                    onChange={(v) => {
                                        setForm((s) => ({ ...s, root_user_phone: v }));
                                        clearInvalidKey("admin.root_user_phone");
                                    }}
                                    inputProps={{ pattern: "^\\+?[0-9\\-\\s()]{6,}$" }}
                                    invalid={invalidKeys.has("admin.root_user_phone")}
                                />
                            )}
                            {switchEmailChecked && (
                                <>
                                    <InputBlock
                                        label={t("install_page.configure.admin_block.admin_email_mail_input_title")}
                                        placeholder={t("install_page.configure.admin_block.admin_email_mail_input_placeholder")}
                                        className={!switchSsoChecked && !anySmsChecked ? "rounded-t-[12px]" : ""}
                                        requiredField
                                        name="root_user_mail"
                                        value={form.root_user_mail}
                                        onChange={(v) => {
                                            setForm((s) => ({ ...s, root_user_mail: v }));
                                            clearInvalidKey("admin.root_user_mail");
                                        }}
                                        type="email"
                                        inputProps={{
                                            onBlur: (e) => {
                                                const val = e.currentTarget.value.trim();

                                                if (val.length < 1) {
                                                    return;
                                                }

                                                if (!isValidEmail(val)) {
                                                    markInvalidKey("admin.root_user_mail");
                                                    return;
                                                }
                                                clearInvalidKey("admin.root_user_mail");
                                            }
                                        }}
                                        invalid={invalidKeys.has("admin.root_user_mail")}
                                    />
                                    <div className="relative w-full flex justify-center">
                                        <Tooltip
                                            classNameContent="max-w-[219px] w-[219px]"
                                            color="orange"
                                            open={mailPasswordErrorVisible}
                                            side="top"
                                            sideOffset={-10}
                                        >
                                            <Text size="s" className="whitespace-pre-line text-center tracking-[-0.15px]">
                                                {t("install_page.configure.admin_block.admin_email_password_input_error")}
                                            </Text>
                                        </Tooltip>
                                        <InputBlock
                                            label={t("install_page.configure.admin_block.admin_email_password_input_title")}
                                            placeholder={t("install_page.configure.admin_block.admin_email_password_input_placeholder")}
                                            className="rounded-b-[12px]"
                                            requiredField
                                            name="root_user_pass"
                                            value={form.root_user_pass}
                                            onChange={(v) => {
                                                setMailPasswordErrorVisible(false);
                                                setForm((s) => ({ ...s, root_user_pass: v }));
                                                clearInvalidKey("admin.root_user_pass");
                                            }}
                                            inputProps={{
                                                onBlur: (e) => {
                                                    const val = e.currentTarget.value.trim();

                                                    if (val.length < 1) {
                                                        return;
                                                    }

                                                    if (val.length < 8 || val.length > 40) {

                                                        markInvalidKey("admin.root_user_pass");
                                                        setMailPasswordErrorVisible(true);
                                                        return;
                                                    }

                                                    setMailPasswordErrorVisible(false);
                                                    clearInvalidKey("admin.root_user_pass");
                                                }
                                            }}
                                            type="password"
                                            invalid={invalidKeys.has("admin.root_user_pass")}
                                        />
                                    </div>
                                </>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
})
AdminBlock.displayName = "AdminBlock";

/* =========================
   Хелперы
   ========================= */

const toFormData = (obj: Record<string, any>) => {
    const data = new FormData();
    for (const [ k, v ] of Object.entries(obj)) {
        if (v === undefined || v === null) continue;
        if (Array.isArray(v)) v.forEach(x => data.append(k, String(x)));
        else if (typeof v === "boolean") data.append(k, v ? "true" : "false");
        else data.append(k, String(v));
    }
    return data;
};

const hasAny = (set: InvalidKeys, keys: string[]) => keys.some((k) => set.has(k));

/* =========================
   Основной контент
   ========================= */

type ConfigureResponseStruct = { success: boolean };
type ValidateResponseStruct = { success: boolean, invalid_keys: string[] };
type RunResponseStruct = { success: boolean, job_id: string };
const PageContentInstallConfigure = () => {
    const t = useLangString();
    const authSettings = useAuthSettings();
    const [ serverSpecsAlert, setServerSpecsAlert ] = useAtom(serverSpecsAlertState);
    const setJobId = useSetAtom(jobIdState);

    const [ domainForm, setDomainForm ] = useAtom(domainFormState);
    const [ authForm, setAuthForm ] = useAtom(authFormState);
    const [ adminForm, setAdminForm ] = useAtom(adminFormState);

    const centerRef = useRef<HTMLDivElement>(null);
    const domainRef = useRef<HTMLDivElement | null>(null);
    const authRef = useRef<HTMLDivElement | null>(null);
    const adminRef = useRef<HTMLDivElement | null>(null);
    const [ activeSection, setActiveSection ] = useState<SectionKey>("domain");
    const [ autoCerts, setAutoCerts ] = useAtom(autoCertsState);
    const [ offerAccepted, setOfferAccepted ] = useState<boolean>(false);
    const [ needShowErrorOfferAccepted, setNeedShowErrorOfferAccepted ] = useState<boolean>(false);
    const [ loading, setLoading ] = useState<boolean>(false);
    const [ networkError, setNetworkError ] = useState(false);
    const { navigateToNextPage } = useNavigatePages();

    const [ isEditing, setIsEditing ] = useState(false);
    const handleFocusCapture = () => setIsEditing(true);
    const handleBlurCapture: FocusEventHandler<HTMLDivElement> = () => {
        // const next = e.relatedTarget as Element | null;
        // если следующий фокус тоже внутри центра - пользователь просто переключился между полями
        // if (next && centerRef.current?.contains(next)) return;
        // фокус ушел из блока ввода – считаем редактирование законченным
        setIsEditing(false);
    };

    const fetchJson = async <T, >(url: string, init: RequestInit, label: string): Promise<T | null> => {
        try {
            const res = await fetch(url, init);
            if (!res.ok) {
                console.log(`Failed to ${label}: ${res.status} ${res.statusText}`);
                return null;
            }
            return (await res.json()) as T;
        } catch (e) {

            // игнорируем AbortError
            // @ts-expect-error
            if (e?.name !== "AbortError") {
                setNetworkError(true);
            }
            throw e;
        }
    };

    // ошибки
    const [ invalidKeys, setInvalidKeys ] = useState<InvalidKeys>(new Set());

    const markInvalidKey = (key: string) => {
        setInvalidKeys((prev) => {
            if (prev.has(key)) return prev;
            const next = new Set(prev);
            next.add(key);
            return next;
        });
    };

    // сброс invalid ключа инпута сразу при изменении поля
    const clearInvalidKey = (key: string) => {
        setInvalidKeys((prev) => {
            if (!prev.has(key)) return prev;
            const next = new Set(prev);
            next.delete(key);
            return next;
        });
    };

    // заполняем методы авторизации/смс провайдеров
    const computeDerived = () => {
        const auth_methods: AuthMethod[] = [];
        if (authSettings.switchEmailChecked) auth_methods.push("mail");
        if (authSettings.switchSsoChecked) auth_methods.push("sso");
        if (authSettings.switchSmsAgentChecked || authSettings.switchVonageChecked || authSettings.switchTwilioChecked) {
            auth_methods.push("phone_number");
        }

        const sms_providers: SmsProvider[] = [];
        if (authSettings.switchSmsAgentChecked) sms_providers.push("sms_agent");
        if (authSettings.switchVonageChecked) sms_providers.push("vonage");
        if (authSettings.switchTwilioChecked) sms_providers.push("twilio");

        const sso_protocol = authSettings.switchSsoChecked ? authSettings.selectedSsoProvider : "";

        return { auth_methods, sms_providers, sso_protocol };
    };

    const validateAll = () => {
        const bad: string[] = [];

        if (!authSettings.switchEmailChecked && !authSettings.switchSsoChecked
            && !authSettings.switchSmsAgentChecked && !authSettings.switchVonageChecked && !authSettings.switchTwilioChecked) {
            bad.push("auth.auth_methods");
        }

        // домен
        if (!domainForm.domain.trim() || !isValidDomain(domainForm.domain.trim())) bad.push("domain.domain");
        if (!autoCerts) {
            if (!domainForm.cert.trim()) bad.push("domain.cert");
            if (!domainForm.private_key.trim()) bad.push("domain.private_key");
        }

        // почта
        if (authSettings.switchEmailChecked) {
            if (!authForm.smtp_host) bad.push("auth.smtp_host");
            if (!authForm.smtp_port) bad.push("auth.smtp_port");
            if (!authForm.smtp_from) {
                bad.push("auth.smtp_from");
            } else {
                if (!isValidEmail(authForm.smtp_from)) bad.push("auth.smtp_from");
            }
        }

        // sso
        if (authSettings.switchSsoChecked) {
            if (!authForm.sso_compass_mapping_name) bad.push("auth.sso_compass_mapping_name");

            if (authSettings.selectedSsoProvider === "oidc") {
                [
                    "oidc_attribution_mapping_mail",
                    "oidc_attribution_mapping_phone_number",
                    "oidc_client_id",
                    "oidc_client_secret",
                    "oidc_oidc_provider_metadata_link",
                ].forEach((k) => {
                    if (!(authForm as any)[k]) bad.push(`auth.${k}`);
                });
            }

            if (authSettings.selectedSsoProvider === "ldap") {
                [
                    "ldap_server_host",
                    "ldap_server_port",
                    "ldap_user_search_base",
                    "ldap_user_unique_attribute",
                    "ldap_user_search_account_dn",
                    "ldap_user_search_account_password",
                ].forEach((k) => {
                    if (!(authForm as any)[k]) bad.push(`auth.${k}`);
                });
            }
        }

        // sms-agent
        if (authSettings.switchSmsAgentChecked) {
            if (!authForm.sms_agent_app_name) bad.push("auth.sms_agent_app_name");
            if (!authForm.sms_agent_login) bad.push("auth.sms_agent_login");
            if (!authForm.sms_agent_password) bad.push("auth.sms_agent_password");
        }

        // vonage
        if (authSettings.switchVonageChecked) {
            if (!authForm.vonage_app_name) bad.push("auth.vonage_app_name");
            if (!authForm.vonage_api_key) bad.push("auth.vonage_api_key");
            if (!authForm.vonage_api_secret) bad.push("auth.vonage_api_secret");
        }

        // twilio
        if (authSettings.switchTwilioChecked) {
            if (!authForm.twilio_app_name) bad.push("auth.twilio_app_name");
            if (!authForm.twilio_account_sid) bad.push("auth.twilio_account_sid");
            if (!authForm.twilio_account_auth_token) bad.push("auth.twilio_account_auth_token");
        }

        // админ
        if (!adminForm.root_user_full_name) bad.push("admin.root_user_full_name");
        if (!adminForm.space_name) bad.push("admin.space_name");
        const anySmsChecked = authSettings.switchSmsAgentChecked || authSettings.switchVonageChecked || authSettings.switchTwilioChecked;
        if (authSettings.switchSsoChecked && !adminForm.root_user_sso_login) bad.push("admin.root_user_sso_login");
        if (anySmsChecked && !adminForm.root_user_phone) bad.push("admin.root_user_phone");
        if (authSettings.switchEmailChecked) {
            if (!adminForm.root_user_mail) {
                bad.push("admin.root_user_mail");
            } else {
                if (!isValidEmail(adminForm.root_user_mail)) bad.push("admin.root_user_mail");
            }
            if (!adminForm.root_user_pass) {
                bad.push("admin.root_user_pass");
            } else {
                if (adminForm.root_user_pass.length < 8 || adminForm.root_user_pass.length > 40) bad.push("admin.root_user_pass");
            }
        }

        return bad;
    };

    // хелперы для статуса в confirmBlock
    const getValueByPath = (path: string): string => {
        if (path.startsWith("domain.")) {
            const k = path.replace("domain.", "") as keyof DomainFormState;
            return String(domainForm[k] ?? "");
        }
        if (path.startsWith("auth.")) {
            const k = path.replace("auth.", "") as keyof AuthFormState;
            // boolean/enum игнорим, тут проверяем только обязательные строковые поля
            return String((authForm as any)[k] ?? "");
        }
        if (path.startsWith("admin.")) {
            const k = path.replace("admin.", "") as keyof AdminFormState;
            return String(adminForm[k] ?? "");
        }
        return "";
    };

    const hasErrorsInSection = (section: SectionKey) => {
        const prefix = `${section}.`;
        for (const k of invalidKeys) {
            if (k.startsWith(prefix)) return true;
        }
        return false;
    };

    const requiredKeysForSection = (section: SectionKey): string[] => {
        if (section === "domain") {
            return [ "domain.domain", ...(autoCerts ? [] : [ "domain.cert", "domain.private_key" ]) ];
        }
        if (section === "auth") {
            const req: string[] = [];
            if (authSettings.switchEmailChecked) {
                req.push("auth.smtp_host", "auth.smtp_port", "auth.smtp_from");
            }
            if (authSettings.switchSsoChecked) {
                req.push("auth.sso_compass_mapping_name");
                if (authSettings.selectedSsoProvider === "oidc") {
                    req.push(
                        "auth.oidc_attribution_mapping_mail",
                        "auth.oidc_attribution_mapping_phone_number",
                        "auth.oidc_client_id",
                        "auth.oidc_client_secret",
                        "auth.oidc_oidc_provider_metadata_link",
                    );
                } else {
                    req.push(
                        "auth.ldap_server_host",
                        "auth.ldap_server_port",
                        "auth.ldap_user_search_base",
                        "auth.ldap_user_unique_attribute",
                        "auth.ldap_user_search_account_dn",
                        "auth.ldap_user_search_account_password",
                    );
                }
            }
            if (authSettings.switchSmsAgentChecked) {
                req.push("auth.sms_agent_app_name", "auth.sms_agent_login", "auth.sms_agent_password");
            }
            if (authSettings.switchVonageChecked) {
                req.push("auth.vonage_app_name", "auth.vonage_api_key", "auth.vonage_api_secret");
            }
            if (authSettings.switchTwilioChecked) {
                req.push("auth.twilio_app_name", "auth.twilio_account_sid", "auth.twilio_account_auth_token");
            }
            return req;
        }

        // admin
        const req: string[] = [ "admin.root_user_full_name", "admin.space_name" ];
        const anySmsChecked = authSettings.switchSmsAgentChecked || authSettings.switchVonageChecked || authSettings.switchTwilioChecked;
        if (authSettings.switchSsoChecked) req.push("admin.root_user_sso_login");
        if (anySmsChecked) req.push("admin.root_user_phone");
        if (authSettings.switchEmailChecked) req.push("admin.root_user_mail", "admin.root_user_pass");
        return req;
    };

    const sectionStatus = (section: SectionKey): blockFilledStatus => {
        const authMethodsNotChecked = !authSettings.switchEmailChecked
            && !authSettings.switchSsoChecked
            && !authSettings.switchSmsAgentChecked && !authSettings.switchVonageChecked && !authSettings.switchTwilioChecked;
        const authMethodsNotCheckedError = invalidKeys.has("auth.auth_methods");
        if (section === "auth" && authMethodsNotCheckedError) return "error-filled";
        if (section === "auth" && authMethodsNotChecked) return "not-filled";
        if (section === "admin" && authMethodsNotChecked) return "not-filled";
        if (hasErrorsInSection(section)) return "error-filled";
        const required = requiredKeysForSection(section);
        if (!required.length) return "success-filled";
        const missing = required.some((k) => !getValueByPath(k)?.trim());
        return missing ? "not-filled" : "success-filled";
    };

    type SectionStatuses = { domain: blockFilledStatus; auth: blockFilledStatus; admin: blockFilledStatus };

    const computeStatuses = (): SectionStatuses => ({
        domain: sectionStatus("domain"),
        auth: sectionStatus("auth"),
        admin: sectionStatus("admin"),
    });

    const [ committedStatuses, setCommittedStatuses ] = useState<SectionStatuses>(() => computeStatuses());

    useEffect(() => {
        if (!isEditing) {
            setCommittedStatuses(computeStatuses());
        }
        // зависимости - все, что влияет на sectionStatus:
        // invalidKeys, domainForm, authForm, adminForm, переключатели authSettings и прочее
    }, [
        isEditing,
        invalidKeys,
        domainForm, authForm, adminForm,
        authSettings.switchEmailChecked,
        authSettings.switchSsoChecked,
        authSettings.switchSmsAgentChecked,
        authSettings.switchVonageChecked,
        authSettings.switchTwilioChecked,
        authSettings.selectedSsoProvider,
        autoCerts,
    ]);

    const statusDomain = committedStatuses.domain;
    const statusAuth = committedStatuses.auth;
    const statusAdmin = committedStatuses.admin;

    const handleSave = async () => {

        if (!offerAccepted) {
            setNeedShowErrorOfferAccepted(true);
        }

        const bad = validateAll();
        setInvalidKeys(new Set(bad));
        if (bad.length > 0) {
            const first = bad[0];
            if (first.startsWith("domain.")) {
                lockActive("domain");
                scrollToRef(domainRef);
            } else if (first.startsWith("auth.")) {
                lockActive("auth");
                scrollToRef(authRef);
            } else if (first.startsWith("admin.")) {
                lockActive("admin");
                scrollToRef(adminRef);
            }
            return;
        }

        if (!offerAccepted) {

            setNeedShowErrorOfferAccepted(true);
            return;
        }

        // собираем итоговый payload
        const payload = {
            ...domainForm,
            ...authForm,
            ...adminForm,
            ...computeDerived(),
            // правим значение для SMTP шифрования (превращаем none в пустую строку)
            smtp_encryption: authForm.smtp_encryption === "none" ? "" : authForm.smtp_encryption,
            ldap_use_ssl: authSettings.checkboxLdapUseSslChecked,
            ldap_account_disabling_monitoring_enabled: authSettings.checkboxAccountDisablingMonitoringEnabledChecked,
        };
        const data = toFormData(payload);

        try {

            setLoading(true);

            const configureJson = await fetchJson<ConfigureResponseStruct>(
                "/api/install/configure",
                { method: "POST", body: data },
                "configure"
            );
            if (!configureJson) return;

            if (configureJson.success) {

                const validateJson = await fetchJson<ValidateResponseStruct>(
                    "/api/install/validate",
                    { method: "POST" },
                    "validate"
                );
                if (!validateJson) return;

                if (Array.isArray(validateJson.invalid_keys)) {
                    setInvalidKeys(normalizeBackendInvalidKeys(new Set(validateJson.invalid_keys)));

                    if (validateJson.success) {

                        const runJson = await fetchJson<RunResponseStruct>(
                            "/api/install/run",
                            { method: "POST" },
                            "run"
                        );
                        if (!runJson) return;

                        if (runJson.success) {
                            setJobId(runJson.job_id);
                            navigateToNextPage();
                        }
                        return;
                    }

                    if (validateJson.invalid_keys.length > 0) {

                        // подсветим первый проблемный блок
                        const first = validateJson.invalid_keys[0];
                        if (first.startsWith("domain.")) {
                            lockActive("domain");
                            scrollToRef(domainRef);
                        } else if (first.startsWith("auth.")) {
                            lockActive("auth");
                            scrollToRef(authRef);
                        } else if (first.startsWith("admin.")) {
                            lockActive("admin");
                            scrollToRef(adminRef);
                        }
                    }
                }
            }
        } finally {
            setLoading(false);
        }
    };


    // плавный скролл к заголовку в рамках centerRef
    const scrollToRef = (ref: RefObject<HTMLDivElement | null>) => {
        const container = centerRef.current;
        const target = ref.current;
        if (!container || !target) return;

        const containerTop = container.getBoundingClientRect().top;
        const targetTop = target.getBoundingClientRect().top;
        const delta = targetTop - containerTop;
        const offset = 68; // высота шапки

        container.scrollTo({
            top: container.scrollTop + delta - offset,
            behavior: "smooth",
        });
    };

    const scrollLockKey = useRef<SectionKey | null>(null);
    const scrollLockUntil = useRef(0);

    // лочим нужный ключ на время анимации
    const lockActive = (key: SectionKey, ms = 800) => {
        scrollLockKey.current = key;
        scrollLockUntil.current = performance.now() + ms;
        setActiveSection(key);

        // авто-сброс лока
        window.setTimeout(() => {
            if (performance.now() >= scrollLockUntil.current) {
                scrollLockKey.current = null;
            }
        }, ms + 50);
    };

    const handleJump = (key: SectionKey) => {

        // мгновенно подсветим выбранный пункт и залочим на время анимации
        lockActive(key);
        if (key === "domain") scrollToRef(domainRef);
        if (key === "auth") scrollToRef(authRef);
        if (key === "admin") scrollToRef(adminRef);
    };

    // подсвечиваем в правой менюшке тот блок что на экране сейчас
    useEffect(() => {
        const container = centerRef.current;
        if (!container) return;

        const computeActive = () => {

            // программный скролл не ломаем
            if (scrollLockKey.current && performance.now() < scrollLockUntil.current) return;
            if (scrollLockKey.current && performance.now() >= scrollLockUntil.current) scrollLockKey.current = null;

            const container = centerRef.current;
            if (!container) return;

            const order: SectionKey[] = [ "domain", "auth", "admin" ];
            const cRect = container.getBoundingClientRect();
            const viewTop = 0;
            const viewBottom = cRect.height;
            const viewCenter = (viewTop + viewBottom) / 2;

            // динамически берём padding-top, чтобы полоса совпадала с визуальной
            const styles = getComputedStyle(container);
            const padTop = parseFloat(styles.paddingTop || "0");

            // ширина "полосы якоря" у верха: от 0 до padTop+16 (минимум 64, максимум 180)
            const ANCHOR_BAND = Math.max(64, Math.min(180, padTop + 16));

            const pairs: Array<[ SectionKey, HTMLElement | null ]> = [
                [ "domain", domainRef.current ],
                [ "auth", authRef.current ],
                [ "admin", adminRef.current ],
            ];
            const entries = pairs.filter(
                (t): t is [ SectionKey, HTMLElement ] => t[1] !== null
            );
            if (!entries.length) return;

            const items = entries.map(([ key, el ]) => {
                const r = el.getBoundingClientRect();
                const topRel = r.top - cRect.top;
                const bottomRel = r.bottom - cRect.top;
                const isVisible = bottomRel > viewTop && topRel < viewBottom;
                const centerDist = Math.abs((topRel + bottomRel) / 2 - viewCenter);
                const edgeDist = Math.min(Math.abs(topRel - viewTop), Math.abs(topRel - viewBottom));
                return { key, topRel, bottomRel, isVisible, centerDist, edgeDist };
            });

            // 1) приоритет: видимые заголовки, у которых верх попал в "якорную" полосу у верха
            const inAnchor = items
                .filter(i => i.isVisible && i.topRel >= viewTop && i.topRel <= ANCHOR_BAND)
                .sort((a, b) =>
                    a.topRel - b.topRel || order.indexOf(a.key) - order.indexOf(b.key)
                );

            let next: SectionKey | null = null;

            if (inAnchor.length) {
                next = inAnchor[0].key;
            } else {
                // 2) иначе — видимые, ближайшие к центру
                const visible = items.filter(i => i.isVisible)
                    .sort((a, b) =>
                        a.centerDist - b.centerDist || order.indexOf(a.key) - order.indexOf(b.key)
                    );
                if (visible.length) {
                    next = visible[0].key;
                } else {
                    // 3) иначе — ближайший к видимой области (верх/низ)
                    next = items
                        .sort((a, b) =>
                            a.edgeDist - b.edgeDist || order.indexOf(a.key) - order.indexOf(b.key)
                        )[0].key;
                }
            }

            if (next) setActiveSection(prev => (prev === next ? prev : next));
        };

        // первый расчёт + подписка
        computeActive();

        let raf = 0;
        const onScroll = () => {
            if (raf) return;
            raf = requestAnimationFrame(() => {
                raf = 0;
                computeActive();
            });
        };

        container.addEventListener("scroll", onScroll, { passive: true });
        return () => {
            container.removeEventListener("scroll", onScroll);
            if (raf) cancelAnimationFrame(raf);
        };
    }, []);

    useEffect(() => {
        const center = () => centerRef.current;

        const scrollCenterBy = (delta: number) => {
            const el = center();
            if (!el) return;
            el.scrollBy({ top: delta, behavior: "auto" });
        };

        const isEditable = (t: EventTarget | null) => {
            if (!(t instanceof HTMLElement)) return false;
            const tag = t.tagName.toLowerCase();
            return (
                t.isContentEditable ||
                tag === "input" ||
                tag === "textarea" ||
                tag === "select"
            );
        };

        const isDialogOpen = () =>
            !!document.querySelector('dialog[open]') ||
            !!document.querySelector('[data-slot="dialog-content"][data-state="open"], [data-slot="dialog-overlay"][data-state="open"]');

        // колесо мыши / трекпад
        const onWheel = (e: WheelEvent) => {
            if (isDialogOpen()) {
                // при открытом диалоге полностью глушим скролл
                e.preventDefault();
                return;
            }
            const el = center();
            if (!el) return;
            // если крутим НЕ по центру — перенаправляем в центр
            if (!el.contains(e.target as Node)) {
                e.preventDefault(); // блокируем скролл body
                scrollCenterBy(e.deltaY);
            }
        };

        // клавиши навигации
        const onKey = (e: KeyboardEvent) => {
            if (isDialogOpen()) {
                // при открытом диалоге игнорим
                e.preventDefault();
                return;
            }
            if (isEditable(e.target)) return; // не мешаем вводу текста
            const el = center();
            if (!el) return;

            let delta: number | null = null;
            const page = el.clientHeight - 40;

            switch (e.key) {
                case "ArrowDown":
                    delta = 40;
                    break;
                case "ArrowUp":
                    delta = -40;
                    break;
                case "PageDown":
                    delta = page;
                    break;
                case "PageUp":
                    delta = -page;
                    break;
                case " ":
                    delta = e.shiftKey ? -page : page;
                    break;
                case "Home":
                    el.scrollTo({ top: 0 });
                    e.preventDefault();
                    return;
                case "End":
                    el.scrollTo({ top: el.scrollHeight });
                    e.preventDefault();
                    return;
            }
            if (delta !== null) {
                e.preventDefault();
                scrollCenterBy(delta);
            }
        };

        // важно: passive: false, чтобы preventDefault сработал
        document.addEventListener("wheel", onWheel, { passive: false });
        document.addEventListener("keydown", onKey);

        return () => {
            document.removeEventListener("wheel", onWheel as any);
            document.removeEventListener("keydown", onKey as any);
        };
    }, []);

    return (
        <div className="flex flex-col w-full h-full">
            <div className="flex flex-row items-start justify-center gap-[32px] w-full h-full px-[48px]">
                <div
                    ref={centerRef}
                    onFocusCapture={handleFocusCapture}
                    onBlurCapture={handleBlurCapture}
                    className="
            flex flex-col items-center justify-start
            grow max-w-[832px]
            h-full overflow-y-auto scrollbar-hidden
            ml-[200px] pt-[116px] pb-[100px]"
                >
                    {serverSpecsAlert === "visible" && (
                        <div
                            className="w-full py-[16px] pl-[22px] pr-[16px] mb-[44px]
                bg-[rgba(255,157,20,0.1)] border-[1px] border-[rgba(255,157,20,0.5)] rounded-[12px]
                flex justify-between"
                        >
                            <div className="flex gap-[16px]">
                                <WarningIcon />
                                <Text className="max-w-[626px] whitespace-pre-line">
                                    {t("install_page.configure.server_specs_warning")
                                        .replace("$VCPU_COUNT", MIN_CPU_COUNT.toString())
                                        .replace("$RAM_COUNT", `${MIN_RAM_MB / 1000}GB`)
                                        .replace("$DISK_SIZE", `${MIN_DISK_SPACE_MB / 1000}GB`)}
                                </Text>
                            </div>
                            <div
                                className="flex items-center justify-center w-[24px] h-[24px]
                  opacity-50 hover:opacity-80 cursor-pointer"
                                onClick={() => setServerSpecsAlert("dismissed")}
                            >
                                <CloseIcon />
                            </div>
                        </div>
                    )}

                    <div className="flex flex-col items-center justify-start gap-[64px]">
                        <DomainBlock
                            ref={domainRef}
                            form={domainForm}
                            setForm={setDomainForm}
                            autoCerts={autoCerts}
                            setAutoCerts={setAutoCerts}
                            invalidKeys={invalidKeys}
                            clearInvalidKey={clearInvalidKey}
                            markInvalidKey={markInvalidKey}
                        />
                        <AuthBlock
                            ref={authRef}
                            {...authSettings}
                            form={authForm}
                            setForm={setAuthForm}
                            invalidKeys={invalidKeys}
                            markInvalidKey={markInvalidKey}
                            clearInvalidKey={clearInvalidKey}
                        />
                        <AdminBlock
                            ref={adminRef}
                            {...authSettings}
                            form={adminForm}
                            setForm={setAdminForm}
                            invalidKeys={invalidKeys}
                            markInvalidKey={markInvalidKey}
                            clearInvalidKey={clearInvalidKey}
                        />
                    </div>
                </div>

                <div className="sticky top-[68px] shrink-0 pt-[48px]">
                    <ConfirmBlock
                        activeSection={activeSection}
                        onJump={handleJump}
                        onSubmit={handleSave}
                        statusDomain={statusDomain}
                        statusAuth={statusAuth}
                        statusAdmin={statusAdmin}
                        setOfferAccepted={setOfferAccepted}
                        needShowErrorOfferAccepted={needShowErrorOfferAccepted}
                        setNeedShowErrorOfferAccepted={setNeedShowErrorOfferAccepted}
                        loading={loading}
                        networkError={networkError}
                        setNetworkError={setNetworkError}
                    />
                </div>
            </div>
        </div>
    );
};

export default PageContentInstallConfigure;
