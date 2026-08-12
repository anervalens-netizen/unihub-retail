import { AppAuthenticatedView } from './AppAuthenticatedView';
import { AvailableMonthsStatus } from './components/AvailableMonthsStatus';
import { useAppController } from './useAppController';

export default function App() {
  const controller = useAppController();
  const { auth, data } = controller;
  if (auth.isLoading || data.availableMonths.isLoading) {
    return <div className="flex h-full items-center justify-center text-sm font-semibold text-slate-500">Se incarca...</div>;
  }
  if (!auth.isAuthenticated) {
    return <div className="flex h-full flex-col items-center justify-center gap-4"><p className="text-sm font-semibold text-slate-500">Nu ești autentificat.</p><button onClick={auth.login} className="rounded bg-blue-600 px-4 py-2 text-white">Login</button></div>;
  }
  const status = data.availableMonths.status;
  if (status === 'empty' || status === 'unavailable' || status === 'session_expired') {
    return <AvailableMonthsStatus status={status} onRetry={() => { void data.availableMonths.retry(); }} />;
  }
  return <AppAuthenticatedView controller={controller} />;
}
