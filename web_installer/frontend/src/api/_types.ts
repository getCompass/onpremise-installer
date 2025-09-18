export type Lang = "ru" | "en" | "de" | "fr" | "es" | "it";

export const INSTALL_STEP_LIST = [ "intall_monolith", "init_monolith", "create_team", "activate_server" ];

export type AuthMethod = "phone_number" | "mail" | "sso";
export type SmsProvider = "sms_agent" | "vonage" | "twilio";
export type SectionKey = "domain" | "auth" | "admin";
export type InvalidKeys = Set<string>;

export interface DomainFormState {
    domain: string;
    cert: string;
    private_key: string;
}

export interface AuthFormState {
    auth_methods: AuthMethod[];
    sms_providers: SmsProvider[];

    sms_agent_app_name: string;
    sms_agent_login: string;
    sms_agent_password: string;

    vonage_app_name: string;
    vonage_api_key: string;
    vonage_api_secret: string;

    twilio_app_name: string;
    twilio_account_sid: string;
    twilio_account_auth_token: string;

    smtp_host: string;
    smtp_port: string;
    smtp_user: string;
    smtp_pass: string;
    smtp_encryption: "none" | "ssl" | "tls";
    smtp_from: string;

    sso_protocol: "" | "oidc" | "ldap";
    sso_compass_mapping_name: string;
    sso_compass_mapping_avatar: string;
    sso_compass_mapping_badge: string;
    sso_compass_mapping_role: string;
    sso_compass_mapping_bio: string;

    oidc_client_id: string;
    oidc_client_secret: string;
    oidc_oidc_provider_metadata_link: string;
    oidc_attribution_mapping_mail: string;
    oidc_attribution_mapping_phone_number: string;

    ldap_server_host: string;
    ldap_server_port: string;
    ldap_use_ssl: boolean;
    ldap_require_cert_strategy: "never" | "allow" | "try" | "demand";
    ldap_user_search_base: string;
    ldap_user_unique_attribute: string;
    ldap_user_search_filter: string;
    ldap_user_search_account_dn: string;
    ldap_user_search_account_password: string;
    ldap_account_disabling_monitoring_enabled: boolean;
}

export interface AdminFormState {
    root_user_sso_login: string;
    root_user_phone: string;
    root_user_full_name: string;
    root_user_mail: string;
    root_user_pass: string;
    space_name: string;
}

export type JobStatus = "running" | "finished" | "error" | "not_found";

export type StatusResponse = {
    success: boolean;
    completed_step_list: string[];
    status: JobStatus;
};