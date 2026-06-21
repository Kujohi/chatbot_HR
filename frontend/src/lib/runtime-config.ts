export type RuntimeConfig = {
  backendUrl: string;
};

declare global {
  interface Window {
    __APP_RUNTIME_CONFIG__?: RuntimeConfig;
  }
}

export function getRuntimeConfig(): RuntimeConfig {
  if (typeof window !== "undefined" && window.__APP_RUNTIME_CONFIG__) {
    return window.__APP_RUNTIME_CONFIG__;
  }

  return {
    backendUrl:
      process.env.NEXT_PUBLIC_BACKEND_URL ??
      process.env.BACKEND_URL ??
      "/api",
  };
}
