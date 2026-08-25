"use client";

import { useEffect, useState } from "react";
import { Button, Input, PageHeader, Select, Table, useToast } from "../../../components/ui";
import { API, authFetch } from "../../../lib/auth";
import { type JobRoleRow, listJobRoles } from "../../../lib/org";

interface PipelineRow {
  id: string;
  name: string;
  rounds: { round_type: string }[];
}

/** R2 — Roles: what interviews are created for. A role binds a pipeline
 * (multi-round) or a plan; assigning candidates to it decides their interview. */
export default function RolesPage() {
  const toast = useToast();
  const [roles, setRoles] = useState<JobRoleRow[] | null>(null);
  const [pipelines, setPipelines] = useState<PipelineRow[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [pipelineId, setPipelineId] = useState("");

  const load = () => listJobRoles().then(setRoles).catch(() => setRoles([]));
  useEffect(() => {
    void load();
    authFetch(`${API}/pipelines`)
      .then(async (r: Response) => (r.ok ? setPipelines((await r.json()) as PipelineRow[]) : null))
      .catch(() => null);
  }, []);

  const create = async () => {
    const resp = await authFetch(`${API}/job-roles`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        description: description || null,
        ...(pipelineId ? { pipeline_id: pipelineId } : {}),
      }),
    });
    if (resp.ok) {
      toast("Role created", "success");
      setName("");
      setDescription("");
      void load();
    } else toast(await resp.text(), "error");
  };

  return (
    <div className="mx-auto max-w-[1000px]">
      <PageHeader title="Roles" subtitle="Each role defines the interview its candidates get." />

      <div className="mt-4 rounded-lg border border-line bg-panel p-4">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <Input
            label="Role name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Backend SDE II"
          />
          <Select
            label="Interview"
            value={pipelineId}
            onChange={(e) => setPipelineId(e.target.value)}
            options={[
              { value: "", label: "Latest plan (default)" },
              ...pipelines.map((p) => ({
                value: p.id,
                label: `Pipeline · ${p.name} (${p.rounds.map((r) => r.round_type).join(" → ")})`,
              })),
            ]}
          />
          <Input
            label="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="optional"
          />
        </div>
        <div className="mt-3">
          <Button
            onClick={create}
            disabledReason={name ? undefined : "The role needs a name first"}
          >
            Create role
          </Button>
        </div>
      </div>

      <div className="mt-4">
        <Table<JobRoleRow>
          columns={[
            {
              key: "name",
              header: "Role",
              sortValue: (r) => r.name.toLowerCase(),
              render: (r) => (
                <div>
                  <div className="font-medium text-ink">{r.name}</div>
                  {r.description && (
                    <div className="text-sm text-muted">{r.description}</div>
                  )}
                </div>
              ),
            },
            {
              key: "interview",
              header: "Interview",
              render: (r) =>
                r.pipeline_name ? (
                  `Pipeline · ${r.pipeline_name}`
                ) : r.plan_id ? (
                  <span className="font-mono text-sm">plan {r.plan_id.slice(0, 8)}</span>
                ) : (
                  <span className="text-muted">latest plan</span>
                ),
            },
            {
              key: "candidates",
              header: "Candidates",
              sortValue: (r) => r.candidates,
              render: (r) => r.candidates,
            },
            {
              key: "created",
              header: "Created",
              sortValue: (r) => r.created_at,
              render: (r) => (
                <span className="font-mono text-sm text-muted">
                  {new Date(r.created_at).toLocaleDateString()}
                </span>
              ),
            },
          ]}
          rows={roles ?? []}
          rowKey={(r) => r.id}
          empty={<span>No roles yet. Create the first one above.</span>}
        />
      </div>
    </div>
  );
}
