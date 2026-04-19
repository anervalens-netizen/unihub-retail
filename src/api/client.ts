import axios from 'axios';

function resolveApiBaseUrl(): string {
  const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL;
  if (configuredBaseUrl) {
    return configuredBaseUrl;
  }

  return '/';
}

const API_BASE_URL = resolveApiBaseUrl();

export const client = axios.create({
  baseURL: API_BASE_URL,
});
