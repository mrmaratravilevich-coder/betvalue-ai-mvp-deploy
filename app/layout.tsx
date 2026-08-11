import type { Metadata } from "next";
import "./globals.css";

const SITE_URL = new URL("https://bvai.onrender.com");

export const metadata: Metadata = {
    metadataBase: SITE_URL,
    title: "BetValue AI — спортивная аналитика",
    description: "Ближайшие матчи по футболу, хоккею и баскетболу, вероятности исходов и понятная оценка надёжности.",
    alternates: {
      canonical: "/",
    },
    robots: {
      index: true,
      follow: true,
    },
    openGraph: {
      title: "BetValue AI — спортивная аналитика",
      description: "Матчи, вероятности исходов и честная оценка неопределённости.",
      url: SITE_URL,
      siteName: "BetValue AI",
      locale: "ru_RU",
      type: "website",
      images: [{ url: "/og.png", width: 1536, height: 1024, alt: "BetValue AI" }],
    },
    twitter: {
      card: "summary_large_image",
      title: "BetValue AI — спортивная аналитика",
      description: "Матчи, вероятности исходов и честная оценка неопределённости.",
      images: ["/og.png"],
    },
  };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <head>
        <script src="https://telegram.org/js/telegram-web-app.js?63" />
      </head>
      <body>{children}</body>
    </html>
  );
}
