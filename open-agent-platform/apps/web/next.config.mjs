import path from "path";

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  // Point to monorepo root for proper file tracing in standalone build
  outputFileTracingRoot: path.join(process.cwd(), "../../"),
};

export default nextConfig;
