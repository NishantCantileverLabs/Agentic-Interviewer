import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Log in — AI Interview",
  description: "Log in to your hiring console or interview home.",
};

export default function LoginLayout({ children }: { children: React.ReactNode }) {
  return children;
}
