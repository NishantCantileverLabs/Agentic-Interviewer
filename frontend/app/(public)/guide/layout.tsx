import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Platform guide - AI Interview",
  description:
    "How the platform works: voice interviews, hands-on rounds, cited evaluations, human review.",
};

export default function GuideLayout({ children }: { children: React.ReactNode }) {
  return children;
}
