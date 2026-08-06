import React, { Component, type ReactNode } from 'react';
import * as Sentry from '@sentry/react';

interface Props {
  children: ReactNode;
  title?: string;
  description?: string;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    void error;
    return { hasError: true };
  }

  override componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    Sentry.captureException(error, { extra: { componentStack: errorInfo.componentStack } });
  }

  private retry = (): void => {
    this.setState({ hasError: false });
  };

  override render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-[320px] items-center justify-center p-6">
          <div className="max-w-lg rounded-3xl border border-red-100 bg-white p-6 text-center shadow-lg dark:border-red-900/40 dark:bg-slate-950">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-50 text-xl text-red-600 dark:bg-red-950/40">
              !
            </div>
            <h1 className="text-xl font-black text-slate-900 dark:text-white">
              {this.props.title ?? 'Ecranul nu a putut fi incarcat'}
            </h1>
            <p className="mt-2 text-sm font-medium text-slate-600 dark:text-slate-300">
              {this.props.description ??
                'Am inregistrat eroarea. Incearca din nou sau reincarca aplicatia.'}
            </p>
            <div className="mt-5 flex flex-col justify-center gap-2 sm:flex-row">
              <button
                type="button"
                onClick={this.retry}
                className="rounded-2xl bg-indigo-600 px-4 py-2 text-sm font-black text-white hover:bg-indigo-700"
              >
                Incearca din nou
              </button>
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="rounded-2xl border border-slate-200 px-4 py-2 text-sm font-black text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-900"
              >
                Reincarca aplicatia
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
