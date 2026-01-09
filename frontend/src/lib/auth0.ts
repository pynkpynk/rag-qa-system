import { initAuth0 as initAuth0Server } from "@auth0/nextjs-auth0";
import type { ConfigParameters } from "@auth0/nextjs-auth0";
import { auth0Config, isAuthConfigured } from "./auth0-config";

export const auth0 = initAuth0Server(auth0Config as ConfigParameters);
export { isAuthConfigured };
