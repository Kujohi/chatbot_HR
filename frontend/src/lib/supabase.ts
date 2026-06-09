import { createClient } from "@supabase/supabase-js";
import { getRuntimeConfig } from "./runtime-config";

const { supabaseUrl, supabaseAnonKey } = getRuntimeConfig();

export const supabase = createClient(supabaseUrl, supabaseAnonKey)
