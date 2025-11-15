/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    // Only proxy API requests if using backend data source
    const dataSource = process.env.NEXT_PUBLIC_DATA_SOURCE || 'backend'
    
    if (dataSource === 'backend') {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      return [
        {
          source: '/api/:path*',
          destination: `${apiUrl}/api/:path*`,
        },
      ]
    }
    
    // No rewrites needed for local data source
    return []
  },
}

module.exports = nextConfig
