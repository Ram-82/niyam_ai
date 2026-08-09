/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // API URL — read at build time for embedded config, overridable at runtime.
  env: {
    NIYAM_API_BASE:
      process.env.NIYAM_API_BASE || "http://localhost:8000",
  },

  async headers() {
    const securityHeaders = [
      // Prevent the page being framed — clickjacking defence.
      { key: "X-Frame-Options", value: "DENY" },
      // Stop browsers sniffing content types.
      { key: "X-Content-Type-Options", value: "nosniff" },
      // Activate browser XSS filter (belt-and-braces alongside CSP).
      { key: "X-XSS-Protection", value: "1; mode=block" },
      // Limit referrer to same-origin for cross-origin navigations.
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      // Opt out of powerful browser features the app doesn't use.
      { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
    ];

    // HSTS only in production — browsers enforce it even after you disable
    // HTTPS, so never send it on a plain HTTP dev server.
    if (process.env.NODE_ENV === "production") {
      securityHeaders.push({
        key: "Strict-Transport-Security",
        // 2 years + includeSubDomains + preload-eligible
        value: "max-age=63072000; includeSubDomains; preload",
      });
    }

    return [{ source: "/(.*)", headers: securityHeaders }];
  },
};

export default nextConfig;
