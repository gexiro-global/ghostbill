/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://backend:8000/v1/:path*",
      },
    ];
  },
  output: "standalone",
};

export default nextConfig;
