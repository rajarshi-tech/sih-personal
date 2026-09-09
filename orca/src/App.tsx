import { useState } from "react";

import { Header } from "@/components/header/Header";
import { NavigationDrawer } from "@/components/navigation/NavigationDrawer";

import { DashboardPage } from "@/pages/DashboardPage";
import { NavigationPage } from "@/pages/NavigationPage";
import { AlertsPage } from "@/pages/AlertsPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { LoginPage } from "@/pages/LoginPage";

import { useLanguage } from "@/lib/i18n";

export interface UserData {
  fullName: string;
  username: string;
}

function App() {
  const { setLanguage } = useLanguage();

  const [user, setUser] = useState<UserData | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [currentPage, setCurrentPage] = useState("dashboard");

  // Show login page if user is not logged in
  if (!user) {
    return (
      <LoginPage
        onLogin={(userData, lang) => {
          setLanguage(lang);
          setUser(userData);
          setCurrentPage("dashboard");
        }}
      />
    );
  }

  // Handles navigation from drawer and pages
  const handleNavigate = (page: string) => {
    if (page === "logout") {
      setUser(null);
      setCurrentPage("dashboard");
      setDrawerOpen(false);
      return;
    }

    setCurrentPage(page);
    setDrawerOpen(false);
  };

  // Handles logout from SettingsPage
  const handleLogout = () => {
    setUser(null);
    setCurrentPage("dashboard");
    setDrawerOpen(false);
  };

  return (
    <div className="h-dvh flex overflow-hidden bg-background">
      {/* Main Content */}
      <main className="flex-1 flex flex-col min-w-0 h-full overflow-hidden bg-transparent relative">
        {/* Header */}
        <Header onMenuClick={() => setDrawerOpen(true)} />

        {/* Dashboard */}
        {currentPage === "dashboard" && <DashboardPage />}

        {/* Navigation */}
        {currentPage === "navigation" && (
          <NavigationPage onNavigate={handleNavigate} />
        )}

        {/* Alerts */}
        {currentPage === "alerts" && <AlertsPage />}

        {/* Settings */}
        {currentPage === "settings" && <SettingsPage onLogout={handleLogout} />}
      </main>

      {/* Navigation Drawer */}
      <NavigationDrawer
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        onNavigate={handleNavigate}
        user={user}
      />
    </div>
  );
}

export default App;
