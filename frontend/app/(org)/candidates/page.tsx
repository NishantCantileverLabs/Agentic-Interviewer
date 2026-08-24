"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { Button, Select, StatusChip, Table, Tooltip } from "../../../components/ui";
import { ALL_STATUSES } from "../../../lib/visibility";
import {
  type CandidacyRow,
  type JobRoleRow,
  listCandidacies,
  listJobRoles,
  toStatus,
} from "../../../lib/org";

/** R5 — Candidates: filter bar, sortable table, §7 chips, same-role compare. */
export default function CandidatesPage() {
  return (
    <Suspense>
      <CandidatesInner />
    </Suspense>
  );
}

function CandidatesInner() {
  const router = useRouter();
  const params = useSearchParams();
  const [rows, setRows] = useState<CandidacyRow[] | null>(null);
  const [roles, setRoles] = useState<JobRoleRow[]>([]);
  const [roleFilter, setRoleFilter] = useState(params.get("role") ?? "");
  const [statusFilter, setStatusFilter] = useState(params.get("status") ?? "");
  const [selected, setSelected] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listCandidacies().then(setRows).catch((e) => setError(String(e.message ?? e)));
    listJobRoles().then(setRoles).catch(() => null);
  }, []);

  const filtered = useMemo(() => {
    if (!rows) return [];
    return rows.filter((r) => {
      if (roleFilter && r.job_role_id !== roleFilter) return false;
      if (statusFilter) {
        const mapped = toStatus(r);
        if (statusFilter === "completed") {
          if (!(mapped === "processing" || mapped === "brief_ready")) return false;
        } else if (mapped !== statusFilter) return false;
      }
      return true;
    });
  }, [rows, roleFilter, statusFilter]);

  const selectedRows = filtered.filter((r) => selected.includes(r.id));
  const compareReady =
    selectedRows.length === 2 &&
    selectedRows.every((r) => r.latest_session_id) &&
    selectedRows[0].job_role_id === selectedRows[1].job_role_id &&
    selectedRows[0].job_role_id !== null;
  const compareBlockReason =
    selectedRows.length !== 2
      ? "Select exactly two candidates to compare"
      : !selectedRows.every((r) => r.latest_session_id)
        ? "Both candidates need a completed interview"
        : "Candidates must be in the same role to compare";

  return (
    <div className="mx-auto max-w-[1100px]">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-xl font-semibold text-ink">Candidates</h1>
          <p className="mt-0.5 text-sm text-muted">
            {rows ? `${filtered.length} of ${rows.length}` : "Loading"} candidacies
          </p>
        </div>
        <div className="flex items-end gap-2">
          <div className="w-44">
            <Select
              label="Role"
              value={roleFilter}
              onChange={(e) => setRoleFilter(e.target.value)}
              options={[
                { value: "", label: "All roles" },
                ...roles.map((r) => ({ value: r.id, label: r.name })),
              ]}
            />
          </div>
          <div className="w-40">
            <Select
              label="Status"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              options={[
                { value: "", label: "All statuses" },
                ...ALL_STATUSES.map((s) => ({ value: s, label: s.replace(/_/g, " ") })),
              ]}
            />
          </div>
          {compareReady ? (
            <Button
              variant="secondary"
              onClick={() =>
                router.push(
                  `/compare?a=${selectedRows[0].latest_session_id}&b=${selectedRows[1].latest_session_id}`,
                )
              }
            >
              Compare
            </Button>
          ) : (
            <Tooltip label={compareBlockReason}>
              <span className="inline-flex">
                <Button variant="secondary" disabled>
                  Compare
                </Button>
              </span>
            </Tooltip>
          )}
        </div>
      </div>

      {error && (
        <p role="alert" className="mt-4 text-sm text-rust">
          Could not load candidates: {error}. Are you logged in with an org account?
        </p>
      )}

      <div className="mt-4">
        <Table<CandidacyRow>
          columns={[
            {
              key: "select",
              header: "",
              width: "36px",
              render: (r) => (
                <input
                  type="checkbox"
                  aria-label={`Select ${r.candidate_name}`}
                  checked={selected.includes(r.id)}
                  onClick={(e) => e.stopPropagation()}
                  onChange={(e) =>
                    setSelected((s) =>
                      e.target.checked ? [...s, r.id] : s.filter((x) => x !== r.id),
                    )
                  }
                  className="h-4 w-4 accent-accent"
                />
              ),
            },
            {
              key: "name",
              header: "Candidate",
              sortValue: (r) => r.candidate_name.toLowerCase(),
              render: (r) => (
                <div>
                  <div className="font-medium text-ink">{r.candidate_name}</div>
                  <div className="font-mono text-xs text-muted">{r.candidate_email}</div>
                </div>
              ),
            },
            {
              key: "role",
              header: "Role",
              sortValue: (r) => r.role_name ?? "",
              render: (r) => r.role_name ?? <span className="text-muted">—</span>,
            },
            {
              key: "status",
              header: "Status",
              sortValue: (r) => r.status,
              render: (r) => <StatusChip status={toStatus(r)} />,
            },
            {
              key: "slot",
              header: "Scheduled",
              sortValue: (r) => r.slot_start ?? "",
              render: (r) =>
                r.slot_start ? (
                  <span className="font-mono text-sm text-ink-soft">
                    {new Date(r.slot_start).toLocaleString(undefined, {
                      month: "short",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                ) : (
                  <span className="text-muted">—</span>
                ),
            },
            {
              key: "updated",
              header: "Invited",
              sortValue: (r) => r.created_at,
              render: (r) => (
                <span className="font-mono text-sm text-muted">
                  {new Date(r.created_at).toLocaleDateString()}
                </span>
              ),
            },
          ]}
          rows={filtered}
          rowKey={(r) => r.id}
          onRowClick={(r) => router.push(`/candidates/${r.id}`)}
          empty={
            <span>
              No candidates match — clear the filters, or invite candidates from the
              Dashboard.
            </span>
          }
        />
      </div>
    </div>
  );
}
