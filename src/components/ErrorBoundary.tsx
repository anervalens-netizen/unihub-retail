// @ts-nocheck
import React, { Component } from 'react';
export class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught:', error, errorInfo);
  }
  render() {
    if (this.state.hasError) {
      return <div className="p-10 text-red-500 bg-red-100"><h1 className="text-2xl font-bold">CRASHED!</h1><pre>{this.state.error?.message}</pre><pre>{this.state.error?.stack}</pre></div>;
    }
    return this.props.children;
  }
}
