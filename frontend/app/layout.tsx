import "./globals.css";
import Providers from "@/components/Providers";

export const metadata = {
  title: "Chips Manager",
  description: "Chips + players accounting",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ru">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
