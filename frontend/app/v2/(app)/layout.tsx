import { Sidebar } from "@/components/v2/shell/Sidebar";
import { TopBar } from "@/components/v2/shell/TopBar";

export default function V2AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "stretch", minHeight: "100vh", background: "var(--bg)" }}>
      <Sidebar />
      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
        <TopBar />
        <main style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
          {children}
        </main>
      </div>
    </div>
  );
}
