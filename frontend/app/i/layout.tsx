import "../styles/tokens.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Your interview",
};

export default function CandidateFlowLayout({ children }: { children: React.ReactNode }) {
  return children;
}
