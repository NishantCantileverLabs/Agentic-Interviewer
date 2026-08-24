import "../styles/tokens.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "AI Interview — structured voice interviews with evidence",
  description:
    "A live voice AI conducts the interview; a second model scores it with cited evidence; a human reviews every assessment.",
};

export default function PublicLayout({ children }: { children: React.ReactNode }) {
  return children;
}
