import axios from "axios"
import { useAuthStore } from "@/store/authStore"

export const apiClient = axios.create({
  // Empty string → relative URLs, proxied by Vite to the backend.
  // Works from any host (localhost, LAN IP) without rebuilding.
  baseURL: import.meta.env.VITE_API_URL || "",
  timeout: 30_000,
})

apiClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

apiClient.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      useAuthStore.getState().clearAuth()
    }
    return Promise.reject(err)
  },
)
