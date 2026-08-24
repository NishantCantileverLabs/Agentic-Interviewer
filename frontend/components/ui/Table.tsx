"use client";

import { useMemo, useState } from "react";
import { cx } from "../../lib/cx";

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => React.ReactNode;
  /** value used for sorting; omit to make the column unsortable */
  sortValue?: (row: T) => string | number;
  width?: string;
}

export interface TableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  /** shown (with its call-to-action) when there are no rows */
  empty?: React.ReactNode;
}

export function Table<T>({ columns, rows, rowKey, onRowClick, empty }: TableProps<T>) {
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col?.sortValue) return rows;
    return [...rows].sort((a, b) => {
      const av = col.sortValue!(a);
      const bv = col.sortValue!(b);
      return av < bv ? -sort.dir : av > bv ? sort.dir : 0;
    });
  }, [rows, sort, columns]);

  const toggle = (key: string) =>
    setSort((s) => (s?.key === key ? { key, dir: s.dir === 1 ? -1 : 1 } : { key, dir: 1 }));

  if (rows.length === 0 && empty) {
    return (
      <div className="rounded-lg border border-line bg-panel p-8 text-center text-muted">
        {empty}
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-line">
      <table className="w-full border-collapse bg-panel text-base">
        <thead>
          <tr className="border-b border-line bg-paper">
            {columns.map((c) => (
              <th
                key={c.key}
                style={c.width ? { width: c.width } : undefined}
                className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted"
              >
                {c.sortValue ? (
                  <button
                    onClick={() => toggle(c.key)}
                    className="inline-flex items-center gap-1 hover:text-ink"
                  >
                    {c.header}
                    <span aria-hidden className="text-xs opacity-70">
                      {sort?.key === c.key ? (sort.dir === 1 ? "▲" : "▼") : "↕"}
                    </span>
                  </button>
                ) : (
                  c.header
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr
              key={rowKey(row)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={cx(
                "border-b border-line last:border-0",
                onRowClick && "cursor-pointer hover:bg-paper",
              )}
            >
              {columns.map((c) => (
                <td key={c.key} className="px-4 py-3 align-middle text-ink">
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
