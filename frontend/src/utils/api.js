import axios from "axios";

const api = axios.create({
  baseURL: process.env.REACT_APP_API_URL || "http://localhost:8000",
  timeout: 30000,
});

api.interceptors.request.use(config => {
  config.headers["X-Client"] = "handscribe-frontend";
  return config;
});

api.interceptors.response.use(
  res => res,
  err => {
    console.error("[API Error]", err.response?.data || err.message);
    return Promise.reject(err);
  }
);

export default api;
