/**
 * MarketplaceLayout — marketplace bo'limi uchun ichki tab navigatsiyasi.
 *
 * Tabs:
 * - Katalog (/marketplace/browse)
 * - Kiruvchi buyurtmalar (/marketplace)
 * - Chiquvchi buyurtmalar (/marketplace/outgoing)
 * - Bannerlar (/marketplace/banners)
 */

import { Tabs } from "@mantine/core";
import { useTranslation } from "react-i18next";
import { Outlet, useLocation, useNavigate } from "react-router-dom";

export function MarketplaceLayout() {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();

  // Joriy tab — yo'ldan aniqlanadi
  const getActiveTab = () => {
    if (location.pathname.startsWith("/marketplace/browse")) return "browse";
    if (location.pathname.startsWith("/marketplace/outgoing")) return "outgoing";
    if (location.pathname.startsWith("/marketplace/banners")) return "banners";
    return "incoming";
  };

  const handleTabChange = (value: string | null) => {
    if (!value) return;
    if (value === "incoming") navigate("/marketplace");
    else navigate(`/marketplace/${value}`);
  };

  return (
    <Tabs value={getActiveTab()} onChange={handleTabChange}>
      <Tabs.List mb="md">
        <Tabs.Tab value="browse">
          {t("marketplace.tabs.browse", { defaultValue: "Katalog" })}
        </Tabs.Tab>
        <Tabs.Tab value="incoming">
          {t("marketplace.tabs.incoming")}
        </Tabs.Tab>
        <Tabs.Tab value="outgoing">
          {t("marketplace.tabs.outgoing")}
        </Tabs.Tab>
        <Tabs.Tab value="banners">
          {t("marketplace.tabs.banners")}
        </Tabs.Tab>
      </Tabs.List>

      <Outlet />
    </Tabs>
  );
}
