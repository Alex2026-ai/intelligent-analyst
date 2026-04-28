import React from 'react';
import { cx } from '../theme';

/**
 * EnterpriseTable — Auditor-grade data table
 *
 * Characteristics:
 * - Row height: 32px
 * - Dense font (11-12px)
 * - Zebra striping (subtle)
 * - Hover highlight
 * - Monospace IDs
 * - Flagged row indicators
 */

interface EnterpriseTableProps {
  children: React.ReactNode;
  className?: string;
}

export function EnterpriseTable({ children, className }: EnterpriseTableProps) {
  return (
    <div className="ia-enterprise-table-wrapper">
      <table className={cx('ia-enterprise-table', className)}>
        {children}
      </table>
    </div>
  );
}

interface TableHeadProps {
  children: React.ReactNode;
}

export function TableHead({ children }: TableHeadProps) {
  return <thead className="ia-enterprise-table__head">{children}</thead>;
}

interface TableBodyProps {
  children: React.ReactNode;
}

export function TableBody({ children }: TableBodyProps) {
  return <tbody className="ia-enterprise-table__body">{children}</tbody>;
}

interface TableRowProps {
  children: React.ReactNode;
  flagged?: boolean;
  onClick?: () => void;
  selected?: boolean;
  className?: string;
}

export function TableRow({ children, flagged, onClick, selected, className }: TableRowProps) {
  return (
    <tr
      className={cx(
        'ia-enterprise-table__row',
        flagged && 'ia-enterprise-table__row--flagged',
        onClick && 'ia-enterprise-table__row--clickable',
        selected && 'ia-enterprise-table__row--selected',
        className
      )}
      onClick={onClick}
    >
      {children}
    </tr>
  );
}

interface TableCellProps {
  children: React.ReactNode;
  align?: 'left' | 'center' | 'right';
  mono?: boolean;
  muted?: boolean;
  truncate?: boolean;
  className?: string;
  title?: string;
}

export function TableCell({
  children,
  align = 'left',
  mono,
  muted,
  truncate,
  className,
  title,
}: TableCellProps) {
  return (
    <td
      className={cx(
        'ia-enterprise-table__cell',
        align === 'right' && 'ia-enterprise-table__cell--right',
        align === 'center' && 'ia-enterprise-table__cell--center',
        mono && 'ia-enterprise-table__cell--mono',
        muted && 'ia-enterprise-table__cell--muted',
        truncate && 'ia-enterprise-table__cell--truncate',
        className
      )}
      title={title}
    >
      {children}
    </td>
  );
}

interface TableHeaderCellProps {
  children: React.ReactNode;
  align?: 'left' | 'center' | 'right';
  className?: string;
}

export function TableHeaderCell({ children, align = 'left', className }: TableHeaderCellProps) {
  return (
    <th
      className={cx(
        'ia-enterprise-table__header',
        align === 'right' && 'ia-enterprise-table__header--right',
        align === 'center' && 'ia-enterprise-table__header--center',
        className
      )}
    >
      {children}
    </th>
  );
}

export default EnterpriseTable;
