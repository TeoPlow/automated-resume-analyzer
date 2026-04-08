/**
 * Auth module — login, logout, session state.
 */
const Auth = (() => {
  let currentUser = null;

  async function login(username, password) {
    const data = await API.post('/auth/login', { username, password });
    API.setTokens(data.data.access_token, data.data.refresh_token);
    await loadUser();
    return currentUser;
  }

  async function loadUser() {
    try {
      const data = await API.get('/me');
      currentUser = data.data;
      return currentUser;
    } catch {
      currentUser = null;
      return null;
    }
  }

  async function logout() {
    try {
      const rt = localStorage.getItem('refresh_token');
      if (rt) {
        await API.post('/auth/logout', { refresh_token: rt }).catch(() => {});
      }
    } finally {
      API.clearTokens();
      currentUser = null;
      App.showLogin();
    }
  }

  function getUser() { return currentUser; }

  function isAdmin() {
    return currentUser?.permissions?.includes('integrations:manage') ?? false;
  }

  function hasPermission(perm) {
    return currentUser?.permissions?.includes(perm) ?? false;
  }

  function isLoggedIn() {
    return !!API.getToken();
  }

  return { login, logout, loadUser, getUser, isAdmin, hasPermission, isLoggedIn };
})();
