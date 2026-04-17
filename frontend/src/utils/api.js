import axios from "axios";

import { useAuthStore } from "@/store/authStore";

const api = axios.create({ withCredentials: true });
let refreshPromise = null;

async function getFreshAccessToken() {
  if (!refreshPromise) {
    refreshPromise = axios
      .post("/api/auth/refresh", {}, { withCredentials: true })
      .then((res) => {
        const token = res.data?.access_token;
        if (!token) throw new Error("Missing access token in refresh response");
        useAuthStore.getState().setAccessToken(token);
        return token;
      })
      .catch((err) => {
        useAuthStore.getState().clear();
        throw err;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (res) => {
    // Avoid empty-body JSON parse issues on 204 No Content (e.g. some DELETE handlers).
    if (res.status === 204 && (res.data === "" || res.data === undefined)) {
      res.data = null;
    }
    return res;
  },
  async (error) => {
    const original = error.config;
    if (!original || original._retry) {
      return Promise.reject(error);
    }
    if (error.response?.status === 401 && !original.url?.includes("/api/auth/refresh")) {
      original._retry = true;
      try {
        const token = await getFreshAccessToken();
        original.headers = original.headers ?? {};
        original.headers.Authorization = `Bearer ${token}`;
        return api(original);
      } catch {
        return Promise.reject(error);
      }
    }
    return Promise.reject(error);
  },
);

export default api;
