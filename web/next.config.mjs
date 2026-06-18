/** @type {import('next').NextConfig} */
const nextConfig = {
  // @marcel/web-tokens and @marcel/icons need transpilation (CSS tokens + icon SVGs).
  // Keep @marcel/web-components out of transpilePackages because SWC cannot parse its CSS nesting inside template literals.
  transpilePackages: ["@marcel/web-tokens", "@marcel/icons"],
  webpack: (config) => {
    return config;
  },
  async rewrites() {
    return [
      {
        source: '/v1/:path*',
        destination: 'http://backend:8000/v1/:path*',
      },
    ];
  },
};

export default nextConfig;
