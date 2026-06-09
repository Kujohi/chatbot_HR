import { getRuntimeConfig } from "./runtime-config";

export const API_BASE = getRuntimeConfig().backendUrl || "/api";
