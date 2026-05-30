// Small firm indicator: red "M" = Mobiup, blue "M" = MobiCell.
// Shared across Focus (top magazine) and Vizite tabs.
export function FirmaBadge({ firma }: { firma: string }) {
  const lower = (firma || '').toLowerCase();
  const color = lower.includes('mobicell') ? '#3b82f6'
              : lower.includes('mobiup')   ? '#ef4444'
              : '#9ca3af';
  return (
    <span
      title={firma}
      style={{ background: color }}
      className="mr-1 inline-flex h-[14px] w-[14px] flex-shrink-0 items-center justify-center rounded-[3px] text-[8px] font-black text-white"
    >
      M
    </span>
  );
}

export default FirmaBadge;
