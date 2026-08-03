import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Матчи — BetValue AI",
  description: "Ближайшие матчи и понятная спортивная аналитика в Telegram.",
  alternates: { canonical: "/telegram" },
  robots: { index: false, follow: false },
};

export default function TelegramLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
