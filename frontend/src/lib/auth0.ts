import { initAuth0 as initAuth0Server } from "@auth0/nextjs-auth0";
import type { ConfigParameters } from "@auth0/nextjs-auth0";
import { buildAuth0Config, isAuthConfigured } from "./auth0-config";

let auth0Instance:
  | ReturnType<typeof initAuth0Server>
  | null = null;

function ensureAuth0() {
  if (!auth0Instance) {
    const config = buildAuth0Config() as ConfigParameters;
    auth0Instance = initAuth0Server(config);
  }
  return auth0Instance;
}

export function getAuth0() {
  if (!isAuthConfigured) {
    throw new Error("Auth0 is not configured");
  }
  return ensureAuth0();
}

export { isAuthConfigured };
