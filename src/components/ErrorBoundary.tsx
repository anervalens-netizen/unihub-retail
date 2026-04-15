import React, { Component, type ReactNode } from 'react';
import { postFrontendError } from '../api/errors';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    postFrontendError({
      message: error.message,
      traceback: error.stack ?? null,
      path: window.location.pathname,
      extra: { componentStack: errorInfo.componentStack },
    });
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="p-10 text-red-500 bg-red-100">
          <h1 className="text-2xl font-bold">CRASHED!</h1>
          <pre>{this.state.error?.message}</pre>
          <pre className="text-xs mt-2 opacity-70">{this.state.error?.stack}</pre>
        </div>
      );
    }
    return this.props.children;
  }
}
