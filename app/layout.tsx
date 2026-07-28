import type { Metadata } from "next";
import { headers } from "next/headers";
import "./globals.css";

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const host = requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host") ?? "localhost:3000";
  const protocol = requestHeaders.get("x-forwarded-proto") ?? (host.startsWith("localhost") || host.startsWith("127.0.0.1") ? "http" : "https");
  const imageUrl = `${protocol}://${host}/og.png`;

  return {
    title: "BetValue AI — спортивная аналитика",
    description: "Ближайшие матчи по футболу и хоккею, вероятности исходов и понятная оценка надёжности.",
    openGraph: {
      title: "BetValue AI — спортивная аналитика",
      description: "Матчи, вероятности исходов и честная оценка неопределённости.",
      images: [{ url: imageUrl, width: 1536, height: 1024, alt: "BetValue AI" }],
    },
    twitter: {
      card: "summary_large_image",
      title: "BetValue AI — спортивная аналитика",
      description: "Матчи, вероятности исходов и честная оценка неопределённости.",
      images: [imageUrl],
    },
  };
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="ru"><body>{children}</body></html>;
}
