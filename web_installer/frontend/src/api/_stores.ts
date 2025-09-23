import { atom } from "jotai";
import type { AdminFormState, AuthFormState, DomainFormState, Lang, StatusResponse } from "@/api/_types.ts";
import { atomWithStorage } from "jotai/utils";

export const INITIAL_DOMAIN_FORM: DomainFormState = {
    domain: "",
    cert: "",
    private_key: "",
};

export const INITIAL_AUTH_FORM: AuthFormState = {
    auth_methods: [],
    sms_providers: [],
    sms_agent_app_name: "",
    sms_agent_login: "",
    sms_agent_password: "",
    vonage_app_name: "",
    vonage_api_key: "",
    vonage_api_secret: "",
    twilio_app_name: "",
    twilio_account_sid: "",
    twilio_account_auth_token: "",
    smtp_host: "",
    smtp_port: "",
    smtp_user: "",
    smtp_pass: "",
    smtp_encryption: "none",
    smtp_from: "",
    sso_protocol: "",
    sso_compass_mapping_name: "",
    sso_compass_mapping_avatar: "",
    sso_compass_mapping_badge: "",
    sso_compass_mapping_role: "",
    sso_compass_mapping_bio: "",
    oidc_client_id: "",
    oidc_client_secret: "",
    oidc_oidc_provider_metadata_link: "",
    oidc_attribution_mapping_mail: "",
    oidc_attribution_mapping_phone_number: "",
    ldap_server_host: "",
    ldap_server_port: "",
    ldap_use_ssl: true,
    ldap_require_cert_strategy: "demand",
    ldap_user_search_base: "",
    ldap_user_unique_attribute: "",
    ldap_user_search_filter: "",
    ldap_user_search_account_dn: "",
    ldap_user_search_account_password: "",
    ldap_account_disabling_monitoring_enabled: false,
};

export const INITIAL_ADMIN_FORM: AdminFormState = {
    root_user_sso_login: "",
    root_user_phone: "",
    root_user_full_name: "",
    root_user_mail: "",
    root_user_pass: "",
    space_name: "",
};

export const langState = atom<Lang>("ru");

export const progressBarState = atom<number>(0);

export const domainFormState = atom<DomainFormState>({ ...INITIAL_DOMAIN_FORM });
export const authFormState = atom<AuthFormState>({ ...INITIAL_AUTH_FORM });
export const adminFormState = atom<AdminFormState>({ ...INITIAL_ADMIN_FORM });

export const switchEmailCheckedState = atom<boolean>(true);
export const switchSsoCheckedState = atom<boolean>(false);
export const selectedSsoProviderState = atom<"oidc" | "ldap">("oidc");
export const switchSmsAgentCheckedState = atom<boolean>(false);
export const switchVonageCheckedState = atom<boolean>(false);
export const switchTwilioCheckedState = atom<boolean>(false);
export const checkboxLdapUseSslCheckedState = atom<boolean | "indeterminate">(true);
export const checkboxAccountDisablingMonitoringEnabledCheckedState = atom<boolean | "indeterminate">(false);
export const autoCertsState = atom<boolean>(true);

export const INITIAL_JOB_STATUS_RESPONSE: StatusResponse = {
    success: true,
    completed_step_list: [],
    status: "running",
}
export const jobStatusResponseState = atom<StatusResponse>(INITIAL_JOB_STATUS_RESPONSE);
export const activateServerStatusState = atom<"not_activated" | "success" | "failed">("not_activated");

// пропускалось ли уже приветственное окно
export const isWelcomeSkippedState = atomWithStorage<number>(
    "is_welcome_skipped",
    JSON.parse(localStorage.getItem("is_welcome_skipped") ?? '0')
);

// видно ли плашку о минимальных характеристиках сервера
export const serverSpecsAlertState = atom<"visible" | "dismissed" | "unknown">("unknown");
export const MIN_CPU_COUNT = 10;
export const MIN_RAM_MB = 16000;
export const MIN_DISK_SPACE_MB = 100000;

export const jobIdState = atomWithStorage<string>(
    "job_id",
    JSON.parse(localStorage.getItem("job_id") ?? '""')
);