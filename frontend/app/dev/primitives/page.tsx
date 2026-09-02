"use client";

import { useState } from "react";
import {
  Button,
  Checkbox,
  Drawer,
  EvidenceChip,
  Input,
  KpiCard,
  Modal,
  Select,
  StatusChip,
  Table,
  Tabs,
  Timeline,
  ToastProvider,
  Tooltip,
  useToast,
} from "../../../components/ui";
import { CandidateShell } from "../../../components/shells/CandidateShell";
import { ALL_STATUSES } from "../../../lib/visibility";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-line pt-5">
      <h2 className="mb-4 font-display text-lg font-semibold text-ink">{title}</h2>
      <div className="flex flex-wrap items-start gap-4">{children}</div>
    </section>
  );
}

interface DemoRow {
  name: string;
  role: string;
  updated: string;
}

const DEMO_ROWS: DemoRow[] = [
  { name: "Priya S.", role: "Backend SDE II", updated: "2026-08-22" },
  { name: "Alex R.", role: "Data Analyst", updated: "2026-08-24" },
  { name: "Sam K.", role: "Backend SDE II", updated: "2026-08-23" },
];

function ToastDemo() {
  const toast = useToast();
  return (
    <>
      <Button variant="secondary" onClick={() => toast("Invite sent", "success")}>
        Success toast
      </Button>
      <Button variant="secondary" onClick={() => toast("Could not reach the server. Retry in a moment", "error")}>
        Error toast
      </Button>
      <Button variant="secondary" onClick={() => toast("Reminder scheduled")}>
        Info toast
      </Button>
    </>
  );
}

export default function PrimitivesPage() {
  const [modalOpen, setModalOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [tab, setTab] = useState("brief");
  const [checked, setChecked] = useState(false);

  return (
    <ToastProvider>
      <div className="mx-auto flex max-w-[960px] flex-col gap-6 px-5 py-8">
        <header>
          <h1 className="font-display text-2xl font-semibold text-ink">Primitives</h1>
          <p className="mt-1 text-muted">
            Every primitive in every state. The F0 reference page. Tokens per DESIGN.md.
          </p>
        </header>

        <Section title="Button">
          <Button>Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="danger">Danger</Button>
          <Button variant="ghost">Ghost</Button>
          <Button loading>Saving</Button>
          <Button disabled>Disabled</Button>
          <Button disabledReason="Available after review">With reason</Button>
          <Button size="sm">Small</Button>
        </Section>

        <Section title="StatusChip: all 9 §7 statuses">
          {ALL_STATUSES.map((s) => (
            <StatusChip key={s} status={s} />
          ))}
        </Section>

        <Section title="Fields">
          <div className="w-64">
            <Input label="Candidate name" placeholder="e.g. Priya S." hint="Shown to reviewers" />
          </div>
          <div className="w-64">
            <Input label="Email" defaultValue="not-an-email" error="Enter a valid email address" />
          </div>
          <div className="w-64">
            <Select
              label="Role"
              options={[
                { value: "", label: "Choose a role" },
                { value: "sde", label: "Backend SDE II" },
              ]}
            />
          </div>
          <Checkbox
            label="Audio recording and AI-assisted assessment (required)"
            checked={checked}
            onChange={(e) => setChecked(e.target.checked)}
          />
          <Checkbox label="With an error" error="This consent is required to continue" />
        </Section>

        <Section title="Modal & Drawer">
          <Button variant="secondary" onClick={() => setModalOpen(true)}>
            Open modal
          </Button>
          <Button variant="secondary" onClick={() => setDrawerOpen(true)}>
            Open drawer
          </Button>
          <Modal
            open={modalOpen}
            onClose={() => setModalOpen(false)}
            title="Withdraw candidate"
            footer={
              <>
                <Button variant="ghost" onClick={() => setModalOpen(false)}>
                  Go back
                </Button>
                <Button variant="danger" onClick={() => setModalOpen(false)}>
                  Withdraw
                </Button>
              </>
            }
          >
            <p className="text-ink-soft">
              This ends the candidacy. The candidate sees a polite end screen; the record is
              kept per your retention policy.
            </p>
          </Modal>
          <Drawer open={drawerOpen} onClose={() => setDrawerOpen(false)} title="Help">
            <p className="text-ink-soft">Device switcher, reconnect, and contact would live here.</p>
          </Drawer>
        </Section>

        <Section title="Tabs">
          <div className="w-full">
            <Tabs
              tabs={[
                { id: "brief", label: "Brief" },
                { id: "replay", label: "Replay" },
                { id: "integrity", label: "Integrity", count: 2 },
                { id: "evaluation", label: "Evaluation" },
              ]}
              active={tab}
              onChange={setTab}
            />
            <div className="p-4 text-muted">Active tab: {tab}</div>
          </div>
        </Section>

        <Section title="Table (sortable) + empty state">
          <div className="w-full">
            <Table<DemoRow>
              columns={[
                { key: "name", header: "Candidate", render: (r) => r.name, sortValue: (r) => r.name },
                { key: "role", header: "Role", render: (r) => r.role, sortValue: (r) => r.role },
                {
                  key: "updated",
                  header: "Updated",
                  render: (r) => <span className="font-mono text-sm text-muted">{r.updated}</span>,
                  sortValue: (r) => r.updated,
                },
              ]}
              rows={DEMO_ROWS}
              rowKey={(r) => r.name}
            />
            <div className="mt-4">
              <Table<DemoRow>
                columns={[{ key: "name", header: "Candidate", render: (r) => r.name }]}
                rows={[]}
                rowKey={(r) => r.name}
                empty={<span>No candidates yet. Send your first invite.</span>}
              />
            </div>
          </div>
        </Section>

        <Section title="Toast">
          <ToastDemo />
        </Section>

        <Section title="Tooltip">
          <Tooltip label="Available after review">
            <Button variant="secondary">Hover or focus me</Button>
          </Tooltip>
        </Section>

        <Section title="Timeline (event rail)">
          <Timeline
            events={[
              { id: "1", at: "09:00:12", label: "Invited", tone: "muted" },
              { id: "2", at: "09:14:03", label: "Consented", detail: "policy 2026-08-23.1" },
              { id: "3", at: "10:02:41", label: "Scheduled", detail: "Tue Aug 25, 08:30" },
              { id: "4", at: "08:31:07", label: "Interview started", tone: "accent" },
            ]}
          />
        </Section>

        <Section title="KpiCard">
          <div className="grid w-full grid-cols-2 gap-4 sm:grid-cols-4">
            <KpiCard label="interviews this week" value={12} />
            <KpiCard label="completion rate" value={84} unit="%" />
            <KpiCard label="awaiting review" value={3} tone="attention" href="/review" />
            <KpiCard label="avg time to complete" value="41" unit="min" />
          </div>
        </Section>

        <Section title="EvidenceChip">
          <EvidenceChip label="“I'd shard by tenant id first”" at="12:41" onSeek={() => {}} />
          <EvidenceChip label="hint level 2 issued" at="18:02" onSeek={() => {}} />
          <EvidenceChip label="score without citation" missing />
        </Section>

        <Section title="CandidateShell (inline preview)">
          <div className="w-full overflow-hidden rounded-lg border border-line">
            <CandidateShell
              orgName="Acme Corp"
              contactEmail="talent@acme.test"
              steps={["What to expect", "Consent", "Schedule", "Confirm"]}
              currentStep={1}
            >
              <div className="rounded-lg border border-line bg-panel p-6 text-center">
                <h2 className="font-display text-lg font-semibold text-ink">Your consent</h2>
                <p className="mt-2 text-ink-soft">One decision per screen.</p>
                <div className="mt-4">
                  <Button>I agree and continue</Button>
                </div>
              </div>
            </CandidateShell>
          </div>
        </Section>
      </div>
    </ToastProvider>
  );
}
