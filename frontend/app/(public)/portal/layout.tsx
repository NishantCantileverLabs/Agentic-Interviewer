import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "My interviews - AI Interview",
};

export default function PortalLayout({ children }: { children: React.ReactNode }) {
  return children;
}
