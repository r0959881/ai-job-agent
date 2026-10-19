import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical, Plus, Trash2 } from "lucide-react";
import * as React from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";

export interface DragHandleProps {
  attributes: ReturnType<typeof useSortable>["attributes"];
  listeners: ReturnType<typeof useSortable>["listeners"];
  label: string;
}

export function DragHandle({ attributes, listeners, label }: DragHandleProps) {
  return (
    <button
      type="button"
      className="flex size-8 shrink-0 cursor-grab touch-none items-center justify-center rounded-md text-muted-foreground hover:bg-muted active:cursor-grabbing"
      aria-label={`Reorder ${label}. Press space, then use the arrow keys.`}
      {...attributes}
      {...listeners}
    >
      <GripVertical className="size-4" />
    </button>
  );
}

function SortableRow({
  id,
  children,
}: {
  id: string;
  children: (handle: Omit<DragHandleProps, "label">, dragging: boolean) => React.ReactNode;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id });
  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn(isDragging && "relative z-10 opacity-80")}
    >
      {children({ attributes, listeners }, isDragging)}
    </div>
  );
}

export function SortableList<T>({
  items,
  getId,
  onMove,
  renderItem,
  className,
}: {
  items: T[];
  getId: (item: T, index: number) => string;
  onMove: (from: number, to: number) => void;
  renderItem: (
    item: T,
    index: number,
    handle: Omit<DragHandleProps, "label">,
    dragging: boolean,
  ) => React.ReactNode;
  className?: string;
}) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const ids = items.map(getId);
  const onDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    onMove(ids.indexOf(String(active.id)), ids.indexOf(String(over.id)));
  };
  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
      <SortableContext items={ids} strategy={verticalListSortingStrategy}>
        <div className={className}>
          {items.map((item, index) => (
            <SortableRow key={ids[index]} id={ids[index]}>
              {(handle, dragging) => renderItem(item, index, handle, dragging)}
            </SortableRow>
          ))}
        </div>
      </SortableContext>
    </DndContext>
  );
}

let idCounter = 0;
const nextId = () => `row-${++idCounter}`;

/** Stable ids for a plain string array so rows keep focus while reordering. */
function syncIds(ids: string[], length: number) {
  while (ids.length < length) ids.push(nextId());
  ids.length = length;
}

function useRowIds(length: number) {
  const ids = React.useRef<string[]>([]);
  syncIds(ids.current, length);
  return ids;
}

/** Editable, reorderable list of strings (bullets, highlights, coursework). */
export function StringListEditor({
  value,
  onChange,
  itemLabel,
  addLabel,
  placeholder,
  multiline = true,
}: {
  value: string[];
  onChange: (next: string[]) => void;
  itemLabel: string;
  addLabel: string;
  placeholder?: string;
  multiline?: boolean;
}) {
  const ids = useRowIds(value.length);
  const focusIndex = React.useRef<number | null>(null);
  const refs = React.useRef<(HTMLTextAreaElement | null)[]>([]);

  React.useEffect(() => {
    if (focusIndex.current != null) {
      refs.current[focusIndex.current]?.focus();
      focusIndex.current = null;
    }
  });

  const update = (index: number, text: string) => onChange(value.map((v, i) => (i === index ? text : v)));
  const remove = (index: number) => {
    ids.current.splice(index, 1);
    onChange(value.filter((_, i) => i !== index));
  };
  const add = (at = value.length) => {
    ids.current.splice(at, 0, nextId());
    focusIndex.current = at;
    onChange([...value.slice(0, at), "", ...value.slice(at)]);
  };

  return (
    <div className="space-y-2">
      <SortableList
        items={value}
        getId={(_, index) => ids.current[index]}
        onMove={(from, to) => {
          ids.current = arrayMove(ids.current, from, to);
          onChange(arrayMove(value, from, to));
        }}
        className="space-y-2"
        renderItem={(text, index, handle) => (
          <div className="flex items-start gap-1">
            <DragHandle {...handle} label={`${itemLabel} ${index + 1}`} />
            <Textarea
              ref={(el) => {
                refs.current[index] = el;
              }}
              value={text}
              rows={multiline ? 2 : 1}
              placeholder={placeholder}
              aria-label={`${itemLabel} ${index + 1}`}
              className={cn("flex-1", !multiline && "min-h-9 resize-none")}
              onChange={(event) => update(index, event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey && (!multiline || event.ctrlKey)) {
                  event.preventDefault();
                  add(index + 1);
                }
              }}
            />
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              onClick={() => remove(index)}
              aria-label={`Remove ${itemLabel.toLowerCase()} ${index + 1}`}
            >
              <Trash2 />
            </Button>
          </div>
        )}
      />
      <Button type="button" variant="outline" size="sm" onClick={() => add()}>
        <Plus /> {addLabel}
      </Button>
    </div>
  );
}
