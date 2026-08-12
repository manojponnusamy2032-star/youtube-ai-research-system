"use client";

import { useEffect, useState } from 'react';
import api from '../../lib/api';
import Loading from '../../components/ui/Loading';

const STORAGE_KEYS = {
  apiBaseUrl: 'settings.apiBaseUrl',
  apiKey: 'settings.apiKey',
  theme: 'settings.theme',
};

type ConnectionStatus = 'idle' | 'testing' | 'success' | 'error';

export default function SettingsPage() {
  const [apiBaseUrl, setApiBaseUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [theme, setTheme] = useState<'light' | 'dark'>('light');
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('idle');
  const [connectionMessage, setConnectionMessage] = useState('');

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const storedApiBaseUrl = localStorage.getItem(STORAGE_KEYS.apiBaseUrl) ?? '';
    const storedApiKey = localStorage.getItem(STORAGE_KEYS.apiKey) ?? '';
    const storedTheme = localStorage.getItem(STORAGE_KEYS.theme) as 'light' | 'dark' | null;

    setApiBaseUrl(storedApiBaseUrl);
    setApiKey(storedApiKey);
    setTheme(storedTheme === 'dark' ? 'dark' : 'light');
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    localStorage.setItem(STORAGE_KEYS.apiBaseUrl, apiBaseUrl);
  }, [apiBaseUrl]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    localStorage.setItem(STORAGE_KEYS.apiKey, apiKey);
  }, [apiKey]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    localStorage.setItem(STORAGE_KEYS.theme, theme);
    document.documentElement.classList.toggle('dark', theme === 'dark');
  }, [theme]);

  useEffect(() => {
    if (apiBaseUrl) {
      api.defaults.baseURL = apiBaseUrl;
    } else {
      api.defaults.baseURL = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';
    }
  }, [apiBaseUrl]);

  const testConnection = async () => {
    setConnectionStatus('testing');
    setConnectionMessage('Testing connection...');

    try {
      const headers = apiKey ? { 'X-API-Key': apiKey } : undefined;
      await api.get('/health', { baseURL: apiBaseUrl || undefined, headers });
      setConnectionStatus('success');
      setConnectionMessage('Connection successful. The API is reachable.');
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Unexpected error during connection test.';
      setConnectionStatus('error');
      setConnectionMessage(`Connection failed: ${message}`);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="mt-2 text-slate-500">Configure API credentials and theme preferences for the dashboard.</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
        <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-900">
          <h2 className="text-xl font-semibold text-slate-900 dark:text-white">API Configuration</h2>
          <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">Set the API endpoint and key used for backend requests.</p>

          <div className="mt-6 space-y-4">
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300">
              API Base URL
              <input
                value={apiBaseUrl}
                onChange={(event) => setApiBaseUrl(event.target.value)}
                placeholder="http://localhost:8000"
                className="mt-2 w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-slate-500 focus:ring-2 focus:ring-slate-200 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:focus:border-slate-500 dark:focus:ring-slate-800"
              />
            </label>

            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300">
              API Key
              <input
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                placeholder="Enter API key"
                className="mt-2 w-full rounded-2xl border border-slate-300 bg-slate-50 px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-slate-500 focus:ring-2 focus:ring-slate-200 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:focus:border-slate-500 dark:focus:ring-slate-800"
              />
            </label>

            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <button
                type="button"
                onClick={testConnection}
                disabled={connectionStatus === 'testing'}
                className="inline-flex items-center justify-center rounded-2xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {connectionStatus === 'testing' ? 'Testing...' : 'Test Connection'}
              </button>
              <p className="text-sm text-slate-500 dark:text-slate-400">Connection tests are run against the configured API base URL.</p>
            </div>

              {connectionStatus === 'testing' && (
                <div className="mt-4">
                  <Loading />
                </div>
              )}

              {connectionStatus !== 'idle' && connectionStatus !== 'testing' && (
              <div
                className={`rounded-2xl border px-4 py-3 text-sm ${
                  connectionStatus === 'success'
                    ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-700 dark:bg-emerald-950 dark:text-emerald-200'
                    : 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-200'
                }`}
              >
                {connectionMessage}
              </div>
            )}
          </div>
        </section>

        <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-900">
          <h2 className="text-xl font-semibold text-slate-900 dark:text-white">Theme</h2>
          <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">Choose the theme for the dashboard.</p>

          <div className="mt-6 flex items-center gap-4">
            <button
              type="button"
              onClick={() => setTheme('light')}
              className={`rounded-2xl px-5 py-3 text-sm font-semibold transition ${
                theme === 'light'
                  ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
                  : 'border border-slate-300 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200'
              }`}
            >
              Light
            </button>
            <button
              type="button"
              onClick={() => setTheme('dark')}
              className={`rounded-2xl px-5 py-3 text-sm font-semibold transition ${
                theme === 'dark'
                  ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
                  : 'border border-slate-300 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200'
              }`}
            >
              Dark
            </button>
          </div>
        </section>
      </div>

      <div className="rounded-3xl border border-slate-200 bg-slate-50 p-6 text-sm text-slate-600 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300">
        <p className="font-medium text-slate-900 dark:text-white">Saved settings locally</p>
        <p className="mt-2">API Base URL, API key, and theme preference are persisted in local storage only and not sent elsewhere.</p>
      </div>
    </div>
  );
}
