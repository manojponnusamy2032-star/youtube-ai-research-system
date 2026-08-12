"use client";
import { Component, ReactNode } from 'react';

type Props = { children: ReactNode };

export default class ErrorBoundary extends Component<Props, { hasError: boolean }> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return <div className="p-6">An unexpected error occurred.</div>;
    }
    return this.props.children;
  }
}
