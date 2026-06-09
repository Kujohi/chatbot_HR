export type RuntimeConfig = {
  backendUrl: string;
  supabaseUrl: string;
  supabaseAnonKey: string;
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
    supabaseUrl:
      process.env.NEXT_PUBLIC_SUPABASE_URL ??
      process.env.SUPABASE_URL ??
      "",
    supabaseAnonKey:
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ??
      process.env.SUPABASE_ANON_KEY ??
      "",
  };
}
