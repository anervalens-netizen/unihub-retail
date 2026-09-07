import { CurrentGrileSubtab } from './grile/CurrentGrileSubtab';

export function GrileSubtab({ initialMonth }: { initialMonth?: string }) {
  return <div className="mx-auto max-w-6xl space-y-4 p-3 pb-24 pt-2 lg:max-w-none lg:p-0">
    <CurrentGrileSubtab initialMonth={initialMonth} />
  </div>;
}
