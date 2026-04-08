/**
 * API client — all HTTP calls to the Gateway.
 */
const API = (() => {
  const BASE = '/api/v1';

  function getToken() {
    return localStorage.getItem('access_token');
  }

  function setTokens(access, refresh) {
    localStorage.setItem('access_token', access);
    localStorage.setItem('refresh_token', refresh);
  }

  function clearTokens() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
  }

  async function request(method, path, { body, query, isFormData } = {}) {
    let url = `${BASE}${path}`;
    if (query) {
      const params = new URLSearchParams();
      for (const [k, v] of Object.entries(query)) {
        if (v !== '' && v !== null && v !== undefined) params.append(k, v);
      }
      const qs = params.toString();
      if (qs) url += `?${qs}`;
    }

    const headers = {};
    const token = getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;

    let fetchBody;
    if (isFormData) {
      fetchBody = body; // FormData, no Content-Type header
    } else if (body) {
      headers['Content-Type'] = 'application/json';
      fetchBody = JSON.stringify(body);
    }

    let res = await fetch(url, { method, headers, body: fetchBody });

    // 401 → try refresh
    if (res.status === 401 && localStorage.getItem('refresh_token')) {
      const refreshed = await refreshToken();
      if (refreshed) {
        headers['Authorization'] = `Bearer ${getToken()}`;
        res = await fetch(url, { method, headers, body: fetchBody });
      } else {
        Auth.logout();
        throw new Error('Session expired');
      }
    }

    if (res.status === 204) return null;

    const data = await res.json();
    if (!res.ok) {
      const msg = data?.error?.message || data?.detail || `HTTP ${res.status}`;
      throw new Error(msg);
    }
    return data;
  }

  async function refreshToken() {
    try {
      const rt = localStorage.getItem('refresh_token');
      if (!rt) return false;
      const res = await fetch(`${BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: rt }),
      });
      if (!res.ok) return false;
      const data = await res.json();
      setTokens(data.data.access_token, data.data.refresh_token);
      return true;
    } catch {
      return false;
    }
  }

  // Convenience methods
  const get = (path, query) => request('GET', path, { query });
  const post = (path, body) => request('POST', path, { body });
  const patch = (path, body) => request('PATCH', path, { body });
  const del = (path) => request('DELETE', path);
  const upload = (path, formData, query) => request('POST', path, { body: formData, isFormData: true, query });

  return { get, post, patch, del, upload, setTokens, clearTokens, getToken, request };
})();
