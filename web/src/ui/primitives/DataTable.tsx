import React from 'react';
import { cx } from '../theme';

interface DataTableProps {
  children: React.ReactNode;
  striped?: boolean;
  compact?: boolean;
  className?: string;
}

/**
 * DataTable — Styled table wrapper for enterprise data grids
 * Features: zebra striping, hover states, compact density
 */
export function DataTable({
  children,
  striped = true,
  compact = true,
  className,
}: DataTableProps) {
  return (
    <div className="ia-table-wrapper">
      <table
        className={cx(
          'ia-table',
          striped && 'ia-table--striped',
          compact && 'ia-table--compact',
          className
        )}
      >
        {children}
      </table>
    </div>
  );
}

interface DataTableHeadProps {
  children: React.ReactNode;
}

export function DataTableHead({ children }: DataTableHeadProps) {
  return <thead className="ia-table__head">{children}</thead>;
}

interface DataTableBodyProps {
  children: React.ReactNode;
}

export function DataTableBody({ children }: DataTableBodyProps) {
  return <tbody className="ia-table__body">{children}</tbody>;
}

interface DataTableRowProps {
  children: React.ReactNode;
  flagged?: boolean;
  onClick?: () => void;
  className?: string;
}

export function DataTableRow({
  children,
  flagged = false,
  onClick,
  className,
}: DataTableRowProps) {
  return (
    <tr
      className={cx(
        'ia-table__row',
        flagged && 'ia-table__row--flagged',
        onClick && 'ia-table__row--clickable',
        className
      )}
      onClick={onClick}
    >
      {children}
    </tr>
  );
}

interface DataTableCellProps {
  children: React.ReactNode;
  align?: 'left' | 'center' | 'right';
  mono?: boolean;
  muted?: boolean;
  truncate?: boolean;
  className?: string;
}

export function DataTableCell({
  children,
  align = 'left',
  mono = false,
  muted = false,
  truncate = false,
  className,
}: DataTableCellProps) {
  return (
    <td
      className={cx(
        'ia-table__cell',
        align === 'right' && 'ia-table__cell--right',
        align === 'center' && 'ia-table__cell--center',
        mono && 'ia-mono-id',
        muted && 'ia-text-muted',
        truncate && 'ia-table__cell--truncate',
        className
      )}
    >
      {children}
    </td>
  );
}

interface DataTableHeaderCellProps {
  children: React.ReactNode;
  align?: 'left' | 'center' | 'right';
  className?: string;
}

export function DataTableHeaderCell({
  children,
  align = 'left',
  className,
}: DataTableHeaderCellProps) {
  return (
    <th
      className={cx(
        'ia-table__header-cell',
        align === 'right' && 'ia-table__header-cell--right',
        align === 'center' && 'ia-table__header-cell--center',
        className
      )}
    >
      {children}
    </th>
  );
}

export default DataTable;
