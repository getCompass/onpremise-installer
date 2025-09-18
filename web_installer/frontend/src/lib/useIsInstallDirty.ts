import { useAtom } from "jotai";
import {
    adminFormState,
    authFormState,
    domainFormState,
    INITIAL_ADMIN_FORM,
    INITIAL_AUTH_FORM,
    INITIAL_DOMAIN_FORM,
} from "@/api/_stores";

const shallowEqual = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

export default function useIsInstallDirty() {
    const [ domainForm ] = useAtom(domainFormState);
    const [ authForm ] = useAtom(authFormState);
    const [ adminForm ] = useAtom(adminFormState);

    const domainDirty = !shallowEqual(domainForm, INITIAL_DOMAIN_FORM);
    const authDirty = !shallowEqual(authForm, INITIAL_AUTH_FORM);
    const adminDirty = !shallowEqual(adminForm, INITIAL_ADMIN_FORM);

    return domainDirty || authDirty || adminDirty;
}
