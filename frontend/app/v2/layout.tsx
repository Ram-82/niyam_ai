import { V2ThemeProvider } from "@/components/v2/theme";

export default function V2Layout({ children }: { children: React.ReactNode }) {
  return <V2ThemeProvider>{children}</V2ThemeProvider>;
}
