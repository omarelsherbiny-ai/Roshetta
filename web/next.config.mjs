/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: false,
  experimental: {
    cpus: 1,
    workerThreads: false,
  },
};

export default nextConfig;
