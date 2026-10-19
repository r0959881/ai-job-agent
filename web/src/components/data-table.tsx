import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type OnChangeFn,
  type RowSelectionState,
  type SortingState,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Accessible table with sortable headers, optional row selection, keyboard row
 * activation and row virtualisation for long lists.
 */
export function DataTable<T>({
  data,
  columns,
  getRowId,
  onRowClick,
  sorting,
  onSortingChange,
  manualSorting = false,
  rowSelection,
  onRowSelectionChange,
  caption,
  virtualizeAbove = 150,
  rowClassName,
}: {
  data: T[];
  columns: ColumnDef<T, unknown>[];
  getRowId: (row: T) => string;
  onRowClick?: (row: T) => void;
  sorting?: SortingState;
  onSortingChange?: OnChangeFn<SortingState>;
  manualSorting?: boolean;
  rowSelection?: RowSelectionState;
  onRowSelectionChange?: OnChangeFn<RowSelectionState>;
  caption: string;
  virtualizeAbove?: number;
  rowClassName?: (row: T) => string | undefined;
}) {
  const [localSorting, setLocalSorting] = React.useState<SortingState>([]);
  const table = useReactTable({
    data,
    columns,
    getRowId,
    state: { sorting: sorting ?? localSorting, rowSelection: rowSelection ?? {} },
    onSortingChange: onSortingChange ?? setLocalSorting,
    onRowSelectionChange,
    enableRowSelection: Boolean(onRowSelectionChange),
    manualSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: manualSorting ? undefined : getSortedRowModel(),
  });
  const rows = table.getRowModel().rows;
  const scroller = React.useRef<HTMLDivElement>(null);
  const virtual = rows.length > virtualizeAbove;
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scroller.current,
    estimateSize: () => 44,
    overscan: 12,
    enabled: virtual,
  });
  const items = virtual ? virtualizer.getVirtualItems() : null;
  const paddingTop = items?.length ? items[0].start : 0;
  const paddingBottom = items?.length ? virtualizer.getTotalSize() - items[items.length - 1].end : 0;
  const visibleRows = items ? items.map((item) => rows[item.index]) : rows;
  const colCount = table.getVisibleLeafColumns().length;

  return (
    <div ref={scroller} className={cn("overflow-auto rounded-lg border", virtual && "max-h-[70vh]")}>
      <table className="w-full caption-bottom text-body">
        <caption className="sr-only">{caption}</caption>
        <thead className="sticky top-0 z-10 bg-muted/95 backdrop-blur">
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id}>
              {group.headers.map((header) => {
                const sortable = header.column.getCanSort();
                const sorted = header.column.getIsSorted();
                return (
                  <th
                    key={header.id}
                    scope="col"
                    aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : undefined}
                    className="h-10 whitespace-nowrap px-3 text-left text-caption font-semibold uppercase tracking-wide text-muted-foreground"
                    style={{ width: header.getSize() !== 150 ? header.getSize() : undefined }}
                  >
                    {header.isPlaceholder ? null : sortable ? (
                      <button
                        type="button"
                        onClick={header.column.getToggleSortingHandler()}
                        className="inline-flex items-center gap-1 rounded hover:text-foreground"
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {sorted === "asc" ? (
                          <ArrowUp className="size-3" />
                        ) : sorted === "desc" ? (
                          <ArrowDown className="size-3" />
                        ) : (
                          <ArrowUpDown className="size-3 opacity-40" />
                        )}
                      </button>
                    ) : (
                      flexRender(header.column.columnDef.header, header.getContext())
                    )}
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {paddingTop > 0 && (
            <tr aria-hidden>
              <td colSpan={colCount} style={{ height: paddingTop }} />
            </tr>
          )}
          {visibleRows.map((row) => (
            <tr
              key={row.id}
              data-state={row.getIsSelected() ? "selected" : undefined}
              className={cn(
                "border-t transition-colors duration-150 data-[state=selected]:bg-accent/60",
                onRowClick && "cursor-pointer hover:bg-muted/60 focus-visible:bg-muted/60",
                rowClassName?.(row.original),
              )}
              tabIndex={onRowClick ? 0 : undefined}
              onClick={(event) => {
                if ((event.target as HTMLElement).closest("button, a, input, [role=checkbox], label")) return;
                onRowClick?.(row.original);
              }}
              onKeyDown={(event) => {
                if (onRowClick && event.key === "Enter" && event.target === event.currentTarget)
                  onRowClick(row.original);
              }}
            >
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className="px-3 py-2 align-middle">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
          {paddingBottom > 0 && (
            <tr aria-hidden>
              <td colSpan={colCount} style={{ height: paddingBottom }} />
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
