/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // API URL — read at build time for embedded config, overridable at runtime.
  env: {
    NIYAM_API_BASE:
      process.env.NIYAM_API_BASE || "http://localhost:8000",
  },
};

export default nextConfig;
