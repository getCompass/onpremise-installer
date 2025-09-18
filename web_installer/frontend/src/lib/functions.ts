import type { InvalidKeys } from "@/api/_types.ts";

const keyMap: Record<string, string> = {
    // domain
    "domain": "domain.domain",
    "nginx.ssl_crt": "domain.cert",
    "nginx.ssl_key": "domain.private_key",

    // auth
    "sms_agent.app_name": "auth.sms_agent_app_name",
    "sms_agent.login": "auth.sms_agent_login",
    "sms_agent.password": "auth.sms_agent_password",
    "vonage.app_name": "auth.vonage_app_name",
    "vonage.api_key": "auth.vonage_api_key",
    "vonage.api_secret": "auth.vonage_api_secret",
    "twilio.app_name": "auth.twilio_app_name",
    "twilio.account_sid": "auth.twilio_account_sid",
    "twilio.account_auth_token": "auth.twilio_account_auth_token",
    "smtp.host": "auth.smtp_host",
    "smtp.port": "auth.smtp_port",
    "smtp.username": "auth.smtp_user",
    "smtp.password": "auth.smtp_pass",
    "smtp.encryption": "auth.smtp_encryption",
    "smtp.from": "auth.smtp_from",
    "sso.protocol": "auth.sso_protocol",
    "sso.compass_mapping.name": "auth.sso_compass_mapping_name",
    "sso.compass_mapping.avatar": "auth.sso_compass_mapping_avatar",
    "sso.compass_mapping.badge": "auth.sso_compass_mapping_badge",
    "sso.compass_mapping.role": "auth.sso_compass_mapping_role",
    "sso.compass_mapping.bio": "auth.sso_compass_mapping_bio",
    "oidc.client_id": "auth.oidc_client_id",
    "oidc.client_secret": "auth.oidc_client_secret",
    "oidc.oidc_provider_metadata_link": "auth.oidc_oidc_provider_metadata_link",
    "oidc.attribution_mapping.mail": "auth.oidc_attribution_mapping_mail",
    "oidc.attribution_mapping.phone_number": "auth.oidc_attribution_mapping_phone_number",
    "ldap.server_host": "auth.ldap_server_host",
    "ldap.server_port": "auth.ldap_server_port",
    "ldap.use_ssl": "auth.ldap_use_ssl",
    "ldap.require_cert_strategy": "auth.ldap_require_cert_strategy",
    "ldap.user_search_base": "auth.ldap_user_search_base",
    "ldap.user_unique_attribute": "auth.ldap_user_unique_attribute",
    "ldap.user_search_filter": "auth.ldap_user_search_filter",
    "ldap.user_search_account_dn": "auth.ldap_user_search_account_dn",
    "ldap.user_search_account_password": "auth.ldap_user_search_account_password",
    "ldap.account_disabling_monitoring_enabled": "auth.ldap_account_disabling_monitoring_enabled",

    // admin
    "root_user.sso_login": "admin.root_user_sso_login",
    "root_user.phone_number": "admin.root_user_phone",
    "root_user.full_name": "admin.root_user_full_name",
    "root_user.mail": "admin.root_user_mail",
    "root_user.password": "admin.root_user_pass",
    "team.init_name": "admin.space_name",
};

export function normalizeBackendInvalidKeys(invalidKeys: InvalidKeys): InvalidKeys {
    const normalized = new Set<string>();

    invalidKeys.forEach(key => {
        if (key in keyMap) {
            normalized.add(keyMap[key]); // заменяем
        } else {
            normalized.add(key); // оставляем без изменений
        }
    });

    return normalized;
}